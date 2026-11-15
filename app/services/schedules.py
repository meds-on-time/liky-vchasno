"""SCRUM-18: intake times per day."""

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Medication, Schedule

MAX_TIMES_PER_DAY = 6


class ScheduleError(ValueError):
    """Invalid schedule; the message is shown to the user."""


def check_min_gap(times: list[time]) -> None:
    """Placeholder for SCRUM-27 (Max): reject intakes closer than 60 minutes."""


def validate_times(times: list[time]) -> list[time]:
    if not times:
        raise ScheduleError("Вкажіть хоча б один час прийому.")
    if len(times) > MAX_TIMES_PER_DAY:
        raise ScheduleError(f"Не більше {MAX_TIMES_PER_DAY} прийомів на день.")
    if len(set(times)) != len(times):
        raise ScheduleError("Час прийому повторюється.")
    times = sorted(times)
    check_min_gap(times)
    return times


def parse_times(raw: list[str]) -> list[time]:
    """'8:00', '20:30' -> time objects."""
    result = []
    for item in raw:
        try:
            hours, minutes = item.strip().split(":")
            result.append(time(int(hours), int(minutes)))
        except ValueError:
            raise ScheduleError(f"Неправильний час: {item}. Формат – ГГ:ХХ, напр. 08:00.")
    return result


async def set_schedule(
    session: AsyncSession, medication_id: int, times: list[time], start_date: date
) -> list[Schedule]:
    """Replace the medication's active schedule with the given times."""
    times = validate_times(times)
    medication = await session.get(Medication, medication_id)
    if medication is None:
        raise LookupError("medication not found")

    old = await session.scalars(
        select(Schedule).where(
            Schedule.medication_id == medication_id, Schedule.is_active.is_(True)
        )
    )
    for schedule in old:
        schedule.is_active = False

    new = [
        Schedule(medication_id=medication_id, time_of_day=t, start_date=start_date)
        for t in times
    ]
    session.add_all(new)
    await session.commit()
    return new


async def get_schedule(session: AsyncSession, medication_id: int) -> list[Schedule]:
    rows = await session.scalars(
        select(Schedule)
        .where(Schedule.medication_id == medication_id, Schedule.is_active.is_(True))
        .order_by(Schedule.time_of_day)
    )
    return list(rows)


async def latest_medication(session: AsyncSession, user_id: int) -> Medication | None:
    return await session.scalar(
        select(Medication)
        .where(Medication.user_id == user_id)
        .order_by(Medication.id.desc())
        .limit(1)
    )