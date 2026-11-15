"""SCRUM-52: reminder rule with a controlled `now`."""

import asyncio
from datetime import date, datetime, time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import get_session
from app.main import app
from app.models import (
    INTAKE_MISSED,
    INTAKE_TAKEN,
    EventLog,
    Intake,
    Medication,
    Schedule,
    TrustedContact,
    User,
)
from app.services import reminders
from app.timeutils import KYIV

DAY = date(2026, 11, 16)


def at(hh: int, mm: int = 0) -> datetime:
    """Kyiv wall-clock time on DAY."""
    return datetime.combine(DAY, time(hh, mm), tzinfo=KYIV)


def run(coro):
    return asyncio.run(coro)


async def setup(sf, with_contact=False, consent=True):
    """Patient with one medication scheduled daily at 20:00."""
    async with sf() as s:
        patient = User(telegram_id=100, name="Олена")
        s.add(patient)
        await s.flush()
        med = Medication(user_id=patient.id, name="Сертралін", dose="50 мг")
        s.add(med)
        await s.flush()
        s.add(Schedule(medication_id=med.id, time_of_day=time(20), start_date=DAY))
        if with_contact:
            contact = User(telegram_id=200, name="Донька")
            s.add(contact)
            await s.flush()
            s.add(TrustedContact(patient_id=patient.id, contact_id=contact.id,
                                 invite_code="abc", consent=consent))
        await s.commit()


async def tick(sf, now):
    async with sf() as s:
        return [(n.kind, n.chat_id) for n in await reminders.tick(s, now)]


async def intake(sf) -> Intake:
    async with sf() as s:
        return (await s.scalars(select(Intake))).one()


async def take(sf, now):
    async with sf() as s:
        return await reminders.take(s, 1, now)


async def snooze(sf, now):
    async with sf() as s:
        return await reminders.snooze(s, 1, now)


def test_no_reminder_before_time(session_factory):
    run(setup(session_factory))
    assert run(tick(session_factory, at(19, 59))) == []


def test_reminder_at_time_creates_pending_intake(session_factory):
    run(setup(session_factory))
    assert run(tick(session_factory, at(20, 0))) == [("regular", 100)]
    assert run(intake(session_factory)).status == "pending"


def test_reminder_is_sent_only_once(session_factory):
    run(setup(session_factory))
    run(tick(session_factory, at(20, 0)))
    assert run(tick(session_factory, at(20, 1))) == []


def test_take_on_time(session_factory):
    run(setup(session_factory))
    run(tick(session_factory, at(20, 0)))
    result, _ = run(take(session_factory, at(20, 3)))
    assert result == "ok"
    assert run(intake(session_factory)).status == INTAKE_TAKEN


def test_second_take_is_already_taken(session_factory):
    run(setup(session_factory))
    run(tick(session_factory, at(20, 0)))
    run(take(session_factory, at(20, 3)))
    result, taken_at = run(take(session_factory, at(20, 5)))
    assert result == "already_taken"
    assert taken_at.astimezone(KYIV).strftime("%H:%M") == "20:03"


def test_take_cancels_repeat_and_alert(session_factory):
    run(setup(session_factory, with_contact=True))
    run(tick(session_factory, at(20, 0)))
    run(take(session_factory, at(20, 10)))
    assert run(tick(session_factory, at(20, 30))) == []
    assert run(tick(session_factory, at(21, 0))) == []


def test_snooze_sends_one_more_reminder_after_10_min(session_factory):
    run(setup(session_factory))
    run(tick(session_factory, at(20, 0)))
    result, _ = run(snooze(session_factory, at(20, 5)))
    assert result == "ok"
    assert run(tick(session_factory, at(20, 14))) == []
    assert run(tick(session_factory, at(20, 15))) == [("snooze", 100)]


def test_snooze_after_t_plus_50_is_too_late(session_factory):
    run(setup(session_factory))
    run(tick(session_factory, at(20, 0)))
    assert run(snooze(session_factory, at(20, 52))) == ("too_late", None)

def test_repeat_at_t_plus_30(session_factory):
    run(setup(session_factory))
    run(tick(session_factory, at(20, 0)))
    assert run(tick(session_factory, at(20, 30))) == [("repeat", 100)]
    assert run(tick(session_factory, at(20, 31))) == []


def test_snooze_near_t_plus_30_gives_one_message_not_two(session_factory):
    run(setup(session_factory))
    run(tick(session_factory, at(20, 0)))
    run(snooze(session_factory, at(20, 25)))  # would fire at 20:35
    assert run(tick(session_factory, at(20, 30))) == [("repeat", 100)]
    assert run(tick(session_factory, at(20, 35))) == []

def test_snooze_does_not_move_missed_time(session_factory):
    run(setup(session_factory))
    run(tick(session_factory, at(20, 0)))
    run(snooze(session_factory, at(20, 45)))
    run(tick(session_factory, at(21, 0)))
    assert run(intake(session_factory)).status == INTAKE_MISSED


def test_missed_at_t_plus_60_alerts_contact_with_consent(session_factory):
    run(setup(session_factory, with_contact=True, consent=True))
    run(tick(session_factory, at(20, 0)))
    assert run(tick(session_factory, at(21, 0))) == [("missed_alert", 200)]
    assert run(tick(session_factory, at(21, 1))) == []


def test_missed_without_consent_sends_no_alert(session_factory):
    run(setup(session_factory, with_contact=True, consent=False))
    run(tick(session_factory, at(20, 0)))
    assert run(tick(session_factory, at(21, 0))) == []
    assert run(intake(session_factory)).status == INTAKE_MISSED


def test_take_after_missed_changes_nothing_but_is_logged(session_factory):
    run(setup(session_factory))
    run(tick(session_factory, at(20, 0)))
    run(tick(session_factory, at(21, 0)))
    assert run(take(session_factory, at(21, 5))) == ("missed", None)
    assert run(intake(session_factory)).status == INTAKE_MISSED

    async def events():
        async with session_factory() as s:
            return list(await s.scalars(select(EventLog.event)))

    assert "taken_after_missed" in run(events())


def test_course_end_date_stops_reminders(session_factory):
    run(setup(session_factory))

    async def end_course():
        async with session_factory() as s:
            sched = await s.get(Schedule, 1)
            sched.end_date = date(2026, 11, 15)
            await s.commit()

    run(end_course())
    assert run(tick(session_factory, at(20, 0))) == []


def test_api_take_and_snooze_and_404(session_factory):
    run(setup(session_factory))

    async def override():
        async with session_factory() as s:
            yield s

    # intake created at a fixed time; API uses real "now", so check only 404 and missed path
    run(tick(session_factory, at(20, 0)))
    app.dependency_overrides[get_session] = override
    try:
        client = TestClient(app)
        assert client.post("/intakes/999/take").status_code == 404
        assert client.post("/intakes/999/snooze").status_code == 404
        body = client.post("/intakes/1/take").json()
        assert body["result"] in {"ok", "missed"}
    finally:
        app.dependency_overrides.clear()