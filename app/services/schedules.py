"""SCRUM-18: intake times per day."""

from datetime import date, time
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Medication, Schedule

MAX_TIMES_PER_DAY = 6
MIN_GAP_MINUTES = 60


class ScheduleError(ValueError):
    """Invalid schedule; the message is shown to the user."""


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def check_min_gap(times: list[time]) -> None:
    """SCRUM-27: neighbouring intakes must be at least 60 minutes apart.

    `times` is sorted. The last intake and the first one of the next day are
    neighbours too (23:30 and 00:10 are only 40 minutes apart).
    """
    if len(times) < 2:
        return
    pairs = list(pairwise(times)) + [(times[-1], times[0])]
    for a, b in pairs:
        gap = (_minutes(b) - _minutes(a)) % (24 * 60)
        if gap < MIN_GAP_MINUTES:
            raise ScheduleError(
                f"Між прийомами має бути щонайменше {MIN_GAP_MINUTES} хв: "
                f"{a:%H:%M} і {b:%H:%M}."
            )


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
    # SCRUM-19: new times keep the course end that was set with /course
    end_date = None
    for schedule in old:
        schedule.is_active = False
        end_date = end_date or schedule.end_date

    new = [
        Schedule(
            medication_id=medication_id,
            time_of_day=t,
            start_date=start_date,
            end_date=end_date,
        )
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