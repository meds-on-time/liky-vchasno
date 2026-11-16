"""SCRUM-40: full intake cycle T -> T+30 -> T+60 on PostgreSQL (scheduler + services)."""

import asyncio
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select

from app.models import (
    INTAKE_MISSED,
    INTAKE_PENDING,
    INTAKE_TAKEN,
    EventLog,
    Intake,
    Medication,
    User,
)
from app.services import reminders
from app.services.contacts import accept_invite, create_invite, set_consent
from app.services.schedules import set_schedule
from app.services.users import register_user
from app.timeutils import KYIV

DAY = date(2026, 11, 17)
PATIENT_TG = 100
CONTACT_TG = 200


def run(coro):
    return asyncio.run(coro)


def at(hh: int, mm: int = 0) -> datetime:
    return datetime.combine(DAY, time(hh, mm), tzinfo=KYIV)


T = at(20)


async def setup_patient(sf, with_contact=False, consent=True) -> int:
    """Patient registered through services, medication with intake at 20:00 Kyiv."""
    async with sf() as s:
        patient, _ = await register_user(s, PATIENT_TG, "Олена")
        med = Medication(user_id=patient.id, name="Сертралін", dose="50 мг", form="таблетка")
        s.add(med)
        await s.commit()
        await set_schedule(s, med.id, [time(20)], DAY)
        if with_contact:
            contact, _ = await register_user(s, CONTACT_TG, "Донька")
            code = await create_invite(s, patient.id)
            assert (await accept_invite(s, code, contact.id))[0] == "ok"
            assert await set_consent(s, patient.id, consent) == 1
        return patient.id


async def tick(sf, now):
    async with sf() as s:
        return [(n.kind, n.chat_id) for n in await reminders.tick(s, now)]


async def only_intake(sf) -> Intake:
    async with sf() as s:
        return (await s.scalars(select(Intake))).one()


async def call(sf, action, intake_id, now):
    async with sf() as s:
        return await action(s, intake_id, now)


async def events(sf) -> list[str]:
    async with sf() as s:
        return list(await s.scalars(select(EventLog.event).order_by(EventLog.id)))


def test_cycle_take_on_time_cancels_repeat_and_missed(pg_session_factory):
    """Цикл T → «Прийняв» → T+30 → T+60: одне нагадування, статус taken, далі тиша"""
    sf = pg_session_factory
    run(setup_patient(sf, with_contact=True))
    assert run(tick(sf, T)) == [("regular", PATIENT_TG)]
    intake = run(only_intake(sf))
    assert intake.status == INTAKE_PENDING

    result, taken_at = run(call(sf, reminders.take, intake.id, T + timedelta(minutes=5)))
    assert result == "ok"
    assert run(tick(sf, T + timedelta(minutes=30))) == []
    assert run(tick(sf, T + timedelta(minutes=60))) == []
    intake = run(only_intake(sf))
    assert intake.status == INTAKE_TAKEN
    assert intake.taken_at == taken_at


def test_cycle_no_answer_repeat_then_missed_alert(pg_session_factory):
    """Цикл без відповіді: T – нагадування, T+30 – повтор, T+60 – пропущено і сигнал"""
    sf = pg_session_factory
    run(setup_patient(sf, with_contact=True, consent=True))
    assert run(tick(sf, T)) == [("regular", PATIENT_TG)]
    assert run(tick(sf, T + timedelta(minutes=29))) == []
    assert run(tick(sf, T + timedelta(minutes=30))) == [("repeat", PATIENT_TG)]
    assert run(tick(sf, T + timedelta(minutes=60))) == [("missed_alert", CONTACT_TG)]
    assert run(tick(sf, T + timedelta(minutes=61))) == []  # the alert is sent once
    assert run(only_intake(sf)).status == INTAKE_MISSED


def test_cycle_consent_off_sends_no_alert(pg_session_factory):
    """Згоду вимкнено (/consent_off): прийом пропущено, але сигналу довіреній особі немає"""
    sf = pg_session_factory
    run(setup_patient(sf, with_contact=True, consent=False))
    run(tick(sf, T))
    run(tick(sf, T + timedelta(minutes=30)))
    assert run(tick(sf, T + timedelta(minutes=60))) == []
    assert run(only_intake(sf)).status == INTAKE_MISSED


def test_cycle_snooze_then_take(pg_session_factory):
    """Відклав о T+5 → нагадування о T+15 → «Прийняв» – taken, повтору на T+30 немає"""
    sf = pg_session_factory
    run(setup_patient(sf))
    run(tick(sf, T))
    intake_id = run(only_intake(sf)).id
    result, remind_at = run(call(sf, reminders.snooze, intake_id, T + timedelta(minutes=5)))
    assert (result, remind_at) == ("ok", (T + timedelta(minutes=15)).astimezone(UTC))
    assert run(tick(sf, T + timedelta(minutes=14))) == []
    assert run(tick(sf, T + timedelta(minutes=15))) == [("snooze", PATIENT_TG)]
    assert run(call(sf, reminders.take, intake_id, T + timedelta(minutes=16)))[0] == "ok"
    assert run(tick(sf, T + timedelta(minutes=30))) == []
    assert run(events(sf)) == ["snoozed", "taken"]


def test_cycle_take_after_t_plus_60_is_logged_only(pg_session_factory):
    """«Прийняв» після T+60: статус лишається missed, у event_log – taken_after_missed"""
    sf = pg_session_factory
    run(setup_patient(sf))
    run(tick(sf, T))
    run(tick(sf, T + timedelta(minutes=60)))
    intake_id = run(only_intake(sf)).id
    assert run(call(sf, reminders.take, intake_id, T + timedelta(minutes=65))) == ("missed", None)
    assert run(call(sf, reminders.snooze, intake_id, T + timedelta(minutes=65))) == (
        "missed", None
    )
    assert run(only_intake(sf)).status == INTAKE_MISSED
    assert run(events(sf))[-1] == "taken_after_missed"


def test_repeated_ticks_create_one_intake_per_time(pg_session_factory):
    """Кілька запусків планувальника в одну хвилину: у PostgreSQL рівно один прийом"""
    sf = pg_session_factory
    run(setup_patient(sf))
    run(tick(sf, T))
    run(tick(sf, T + timedelta(seconds=30)))
    run(tick(sf, T + timedelta(minutes=1)))

    async def count():
        async with sf() as s:
            return await s.scalar(select(func.count()).select_from(Intake))

    assert run(count()) == 1


def test_times_are_stored_in_utc_and_shown_in_kyiv(pg_session_factory):
    """Час прийому в PostgreSQL зберігається з часовою зоною: 20:00 Київ = 18:00 UTC"""
    sf = pg_session_factory
    run(setup_patient(sf))
    run(tick(sf, T))
    scheduled = run(only_intake(sf)).scheduled_at
    assert scheduled.tzinfo is not None
    assert scheduled.astimezone(UTC).strftime("%H:%M") == "18:00"
    assert scheduled.astimezone(KYIV).strftime("%H:%M") == "20:00"


def test_repeated_start_makes_no_duplicate_user(pg_session_factory):
    """Повторний /start (register_user) у PostgreSQL не створює другого користувача"""
    sf = pg_session_factory

    async def scenario():
        async with sf() as s:
            first, created1 = await register_user(s, PATIENT_TG, "Олена")
            second, created2 = await register_user(s, PATIENT_TG, "Олена")
            total = await s.scalar(select(func.count()).select_from(User))
            return created1, created2, first.id == second.id, total

    assert run(scenario()) == (True, False, True, 1)
