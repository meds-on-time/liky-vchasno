"""SCRUM-19: course duration (N days) for a medication.

The scheduler already stops reminding after schedules.end_date
(reminders._create_due_intakes), so this module only sets that date.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Schedule

MAX_COURSE_DAYS = 365
OFF_WORDS = ("0", "off")


class CourseError(ValueError):
    """Invalid course duration; the message is shown to the user."""


def parse_course_days(raw: str | None) -> int | None:
    """'14' -> 14; '0' or 'off' -> None (no end date)."""
    value = (raw or "").strip().casefold()
    if value in OFF_WORDS:
        return None
    if not value.isdigit():
        raise CourseError(
            f"Напишіть кількість днів від 1 до {MAX_COURSE_DAYS}, напр.: /course 14. "
            "Щоб прибрати кінець курсу: /course off"
        )
    days = int(value)
    if not 1 <= days <= MAX_COURSE_DAYS:
        raise CourseError(f"Тривалість курсу – від 1 до {MAX_COURSE_DAYS} днів.")
    return days


def course_end_date(today: date, days: int | None) -> date | None:
    """Last day of the course: today counts as day 1, so N days end on today + N - 1."""
    if days is None:
        return None
    return today + timedelta(days=days - 1)


async def _active_schedules(session: AsyncSession, medication_id: int) -> list[Schedule]:
    rows = await session.scalars(
        select(Schedule).where(
            Schedule.medication_id == medication_id, Schedule.is_active.is_(True)
        )
    )
    return list(rows)


async def set_course_end(
    session: AsyncSession, medication_id: int, end_date: date | None
) -> None:
    """Set (or clear with None) the course end for all active intake times."""
    schedules = await _active_schedules(session, medication_id)
    if not schedules:
        raise CourseError("Спершу задайте час прийомів: /times 08:00 20:00")
    for schedule in schedules:
        schedule.end_date = end_date
    await session.commit()


async def course_end(session: AsyncSession, medication_id: int) -> date | None:
    """Course end of the active schedule, or None if the course is open-ended."""
    schedules = await _active_schedules(session, medication_id)
    ends = [s.end_date for s in schedules if s.end_date is not None]
    return max(ends) if ends else None
