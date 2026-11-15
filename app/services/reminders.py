"""SCRUM-52: reminder rule.

Intake at T: reminder at T, missed at T+60 (repeat at T+30 is SCRUM-25).
Snooze sends one more reminder after 10 min and does not move T+30 / T+60.
Snooze is not allowed from T+50. 'Taken' after T+60 changes nothing.
Every function gets `now` as a parameter so tests can control time.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    INTAKE_MISSED,
    INTAKE_PENDING,
    INTAKE_TAKEN,
    EventLog,
    Intake,
    Medication,
    Schedule,
    TrustedContact,
    User,
)
from app.timeutils import KYIV, as_utc, kyiv_datetime

MISSED_AFTER = timedelta(minutes=60)
SNOOZE_FOR = timedelta(minutes=10)
SNOOZE_DEADLINE = timedelta(minutes=50)


@dataclass
class Notification:
    """What the bot has to send. kind: regular | snooze | missed_alert."""

    kind: str
    chat_id: int
    intake: Intake
    medication: Medication
    patient_name: str | None = None


# ---------- user actions (API) ----------


async def take(session: AsyncSession, intake_id: int, now: datetime):
    """Returns (result, taken_at) or None if the intake does not exist."""
    now = as_utc(now)
    intake = await session.get(Intake, intake_id)
    if intake is None:
        return None
    if intake.status == INTAKE_TAKEN:
        return "already_taken", as_utc(intake.taken_at)
    if intake.status == INTAKE_MISSED or now >= as_utc(intake.scheduled_at) + MISSED_AFTER:
        session.add(EventLog(intake_id=intake.id, event="taken_after_missed"))
        await session.commit()
        return "missed", None

    intake.status = INTAKE_TAKEN
    intake.taken_at = now
    intake.snoozed_until = None
    session.add(EventLog(intake_id=intake.id, event="taken"))
    await session.commit()
    return "ok", now


async def snooze(session: AsyncSession, intake_id: int, now: datetime):
    """Returns (result, remind_at) or None if the intake does not exist.

    result 'too_late' = snooze pressed after T+50 (old message button).
    """
    now = as_utc(now)
    intake = await session.get(Intake, intake_id)
    if intake is None:
        return None
    if intake.status == INTAKE_TAKEN:
        return "already_taken", None
    t = as_utc(intake.scheduled_at)
    if intake.status == INTAKE_MISSED or now >= t + MISSED_AFTER:
        return "missed", None
    if now >= t + SNOOZE_DEADLINE:
        return "too_late", None

    intake.snoozed_until = now + SNOOZE_FOR
    session.add(EventLog(intake_id=intake.id, event="snoozed"))
    await session.commit()
    return "ok", intake.snoozed_until


# ---------- scheduler tick ----------


async def _create_due_intakes(session: AsyncSession, now: datetime) -> list[Intake]:
    """Create today's intakes whose time has come (within the T..T+60 window)."""
    today = now.astimezone(KYIV).date()
    schedules = await session.scalars(
        select(Schedule).where(Schedule.is_active.is_(True), Schedule.start_date <= today)
    )
    created = []
    for schedule in schedules:
        if schedule.end_date is not None and today > schedule.end_date:
            continue
        t = kyiv_datetime(today, schedule.time_of_day)
        if not (t <= now < t + MISSED_AFTER):
            continue
        exists = await session.scalar(
            select(Intake.id).where(
                Intake.schedule_id == schedule.id, Intake.scheduled_at == t
            )
        )
        if exists is None:
            intake = Intake(schedule_id=schedule.id, scheduled_at=t, status=INTAKE_PENDING)
            session.add(intake)
            created.append(intake)
    await session.flush()
    return created


async def _patient(session: AsyncSession, intake: Intake) -> tuple[Medication, User]:
    schedule = await session.get(Schedule, intake.schedule_id)
    medication = await session.get(Medication, schedule.medication_id)
    user = await session.get(User, medication.user_id)
    return medication, user


async def _alert_chats(session: AsyncSession, patient_id: int) -> list[int]:
    """Telegram ids of trusted contacts who are linked and have consent."""
    rows = await session.scalars(
        select(User.telegram_id)
        .join(TrustedContact, TrustedContact.contact_id == User.id)
        .where(TrustedContact.patient_id == patient_id, TrustedContact.consent.is_(True))
    )
    return list(rows)


async def tick(session: AsyncSession, now: datetime) -> list[Notification]:
    """One scheduler step: update intakes and return what has to be sent."""
    now = as_utc(now)
    out: list[Notification] = []

    for intake in await _create_due_intakes(session, now):
        med, user = await _patient(session, intake)
        out.append(Notification("regular", user.telegram_id, intake, med))

    pending = await session.scalars(select(Intake).where(Intake.status == INTAKE_PENDING))
    for intake in list(pending):
        t = as_utc(intake.scheduled_at)
        if now < t:
            continue
        med, user = await _patient(session, intake)

        # T+60: missed, alert trusted contacts with consent
        if now >= t + MISSED_AFTER:
            intake.status = INTAKE_MISSED
            intake.snoozed_until = None
            if not intake.missed_alert_sent:
                intake.missed_alert_sent = True
                for chat_id in await _alert_chats(session, user.id):
                    out.append(Notification("missed_alert", chat_id, intake, med, user.name))
            continue

        if intake.snoozed_until is not None and now >= as_utc(intake.snoozed_until):
            intake.snoozed_until = None
            out.append(Notification("snooze", user.telegram_id, intake, med))

    await session.commit()
    return out