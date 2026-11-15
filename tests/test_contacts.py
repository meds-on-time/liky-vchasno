"""SCRUM-14, SCRUM-15: trusted contact invite and consent."""

import asyncio
from datetime import date, datetime, time

from sqlalchemy import select

from app.bot_contacts import invite_link
from app.models import EventLog, Medication, Schedule, TrustedContact, User
from app.services import contacts, reminders
from app.timeutils import KYIV

DAY = date(2026, 11, 16)


def at(hh: int, mm: int = 0) -> datetime:
    return datetime.combine(DAY, time(hh, mm), tzinfo=KYIV)


def run(coro):
    return asyncio.run(coro)


async def add_users(sf):
    """Patient (id 1, tg 100) with a 20:00 medication, contact (id 2, tg 200), stranger (id 3)."""
    async with sf() as s:
        patient = User(telegram_id=100, name="Олена")
        contact = User(telegram_id=200, name="Донька")
        stranger = User(telegram_id=300, name="Інший")
        s.add_all([patient, contact, stranger])
        await s.flush()
        med = Medication(user_id=patient.id, name="Сертралін", dose="50 мг")
        s.add(med)
        await s.flush()
        s.add(Schedule(medication_id=med.id, time_of_day=time(20), start_date=DAY))
        await s.commit()


async def invite(sf, patient_id=1):
    async with sf() as s:
        return await contacts.create_invite(s, patient_id)


async def accept(sf, code, contact_id=2):
    async with sf() as s:
        result, patient = await contacts.accept_invite(s, code, contact_id)
        return result, patient.id if patient else None


async def consent(sf, value, patient_id=1):
    async with sf() as s:
        return await contacts.set_consent(s, patient_id, value)


async def rows(sf):
    async with sf() as s:
        return list(await s.scalars(select(TrustedContact)))


async def tick(sf, now):
    async with sf() as s:
        return [(n.kind, n.chat_id) for n in await reminders.tick(s, now)]


def test_create_invite_makes_unlinked_row_without_consent(session_factory):
    run(add_users(session_factory))
    code = run(invite(session_factory))
    [row] = run(rows(session_factory))
    assert row.invite_code == code
    assert row.patient_id == 1
    assert row.contact_id is None
    assert row.consent is False


def test_invite_codes_are_unique(session_factory):
    run(add_users(session_factory))
    assert run(invite(session_factory)) != run(invite(session_factory))


def test_invite_link_format():
    assert invite_link("liky_bot", "abc") == "https://t.me/liky_bot?start=inv_abc"


def test_accept_invite_links_contact(session_factory):
    run(add_users(session_factory))
    code = run(invite(session_factory))
    assert run(accept(session_factory, code)) == ("ok", 1)
    [row] = run(rows(session_factory))
    assert row.contact_id == 2
    assert row.consent is False


def test_invite_code_is_one_time(session_factory):
    run(add_users(session_factory))
    code = run(invite(session_factory))
    run(accept(session_factory, code, contact_id=2))
    assert run(accept(session_factory, code, contact_id=3)) == ("already_used", 1)
    [row] = run(rows(session_factory))
    assert row.contact_id == 2


def test_own_link_is_rejected(session_factory):
    run(add_users(session_factory))
    code = run(invite(session_factory))
    assert run(accept(session_factory, code, contact_id=1)) == ("self", 1)
    [row] = run(rows(session_factory))
    assert row.contact_id is None


def test_unknown_code_is_not_found(session_factory):
    run(add_users(session_factory))
    assert run(accept(session_factory, "nope")) == ("not_found", None)


def test_same_contact_is_not_linked_twice(session_factory):
    run(add_users(session_factory))
    run(accept(session_factory, run(invite(session_factory))))
    second = run(invite(session_factory))
    assert run(accept(session_factory, second)) == ("already_linked", 1)
    linked = [r for r in run(rows(session_factory)) if r.contact_id is not None]
    assert len(linked) == 1


def test_consent_without_linked_contacts_changes_nothing(session_factory):
    run(add_users(session_factory))
    run(invite(session_factory))  # invite sent, but nobody opened it
    assert run(consent(session_factory, True)) == 0
    assert run(rows(session_factory))[0].consent is False


def test_consent_on_and_off(session_factory):
    run(add_users(session_factory))
    run(accept(session_factory, run(invite(session_factory))))
    assert run(consent(session_factory, True)) == 1
    assert run(rows(session_factory))[0].consent is True
    assert run(consent(session_factory, False)) == 1
    assert run(rows(session_factory))[0].consent is False


def test_consent_is_logged(session_factory):
    run(add_users(session_factory))
    run(accept(session_factory, run(invite(session_factory))))
    run(consent(session_factory, True))
    run(consent(session_factory, False))

    async def events():
        async with session_factory() as s:
            return list(await s.scalars(select(EventLog.event).order_by(EventLog.id)))

    assert run(events()) == ["invite_created", "invite_accepted", "consent_on", "consent_off"]


def test_missed_intake_alerts_contact_after_consent_on(session_factory):
    run(add_users(session_factory))
    run(accept(session_factory, run(invite(session_factory))))
    run(consent(session_factory, True))
    run(tick(session_factory, at(20, 0)))
    assert run(tick(session_factory, at(21, 0))) == [("missed_alert", 200)]


def test_no_alert_after_consent_off(session_factory):
    run(add_users(session_factory))
    run(accept(session_factory, run(invite(session_factory))))
    run(consent(session_factory, True))
    run(consent(session_factory, False))
    run(tick(session_factory, at(20, 0)))
    assert run(tick(session_factory, at(21, 0))) == []


def test_no_alert_before_invite_is_accepted(session_factory):
    run(add_users(session_factory))
    run(invite(session_factory))
    run(consent(session_factory, True))
    run(tick(session_factory, at(20, 0)))
    assert run(tick(session_factory, at(21, 0))) == []
