"""SCRUM-22/23: helpers for the reminder buttons."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Intake, Medication, Schedule, User


async def owner_telegram_id(session: AsyncSession, intake_id: int) -> int | None:
    """Telegram id of the patient the intake belongs to, or None if there is no such intake."""
    return await session.scalar(
        select(User.telegram_id)
        .join(Medication, Medication.user_id == User.id)
        .join(Schedule, Schedule.medication_id == Medication.id)
        .join(Intake, Intake.schedule_id == Schedule.id)
        .where(Intake.id == intake_id)
    )
