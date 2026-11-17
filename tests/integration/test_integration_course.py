"""SCRUM-71 (tests for SCRUM-19): course duration on PostgreSQL.

The course end is a DATE in Kyiv time, while intakes are stored in UTC.
Around midnight the Kyiv date and the UTC date differ, so the boundary is
checked on the real database.
"""

import asyncio
from datetime import date, datetime, time

from sqlalchemy import select

from app.models import Medication, Schedule, User
from app.services import reminders
from app.services.courses import course_end, course_end_date, set_course_end
from app.services.medications import describe_medications
from app.services.schedules import set_schedule
from app.timeutils import KYIV

TODAY = date(2026, 11, 18)


def run(coro):
    return asyncio.run(coro)


async def medication_with_times(sf, times) -> tuple[int, int]:
    async with sf() as s:
        user = User(telegram_id=100, name="Олена")
        s.add(user)
        await s.flush()
        med = Medication(user_id=user.id, name="Сертралін", dose="50 мг", form="таблетка")
        s.add(med)
        await s.commit()
        await set_schedule(s, med.id, list(times), TODAY)
        return user.id, med.id


async def set_end(sf, med_id, end):
    async with sf() as s:
        await set_course_end(s, med_id, end)


async def tick_kinds(sf, day, at):
    async with sf() as s:
        now = datetime.combine(day, at, tzinfo=KYIV)
        return [n.kind for n in await reminders.tick(s, now)]


def test_course_end_after_midnight_uses_kyiv_date(pg_session_factory):
    """Прийом о 00:30 за Києвом (22:30 UTC попереднього дня): останній день курсу ще нагадує, наступний – ні"""
    sf = pg_session_factory
    _, med_id = run(medication_with_times(sf, [time(0, 30)]))
    run(set_end(sf, med_id, course_end_date(TODAY, 3)))  # 18, 19, 20.11
    assert run(tick_kinds(sf, date(2026, 11, 20), time(0, 30))) == ["regular"]
    assert run(tick_kinds(sf, date(2026, 11, 21), time(0, 30))) == []


def test_course_end_late_evening_last_day(pg_session_factory):
    """Прийом о 23:45 за Києвом в останній день курсу ще створює нагадування"""
    sf = pg_session_factory
    _, med_id = run(medication_with_times(sf, [time(23, 45)]))
    run(set_end(sf, med_id, course_end_date(TODAY, 1)))  # лише сьогодні
    assert run(tick_kinds(sf, TODAY, time(23, 45))) == ["regular"]
    assert run(tick_kinds(sf, date(2026, 11, 19), time(23, 45))) == []


def test_course_end_stored_as_date_for_all_times(pg_session_factory):
    """/course N у PostgreSQL: end_date однаковий для всіх активних часів, тип – дата без часу"""
    sf = pg_session_factory
    _, med_id = run(medication_with_times(sf, [time(8), time(20)]))
    run(set_end(sf, med_id, course_end_date(TODAY, 14)))

    async def ends():
        async with sf() as s:
            return list(
                await s.scalars(
                    select(Schedule.end_date).where(
                        Schedule.medication_id == med_id, Schedule.is_active.is_(True)
                    )
                )
            )

    assert run(ends()) == [date(2026, 12, 1), date(2026, 12, 1)]


def test_new_times_keep_course_and_off_clears_it(pg_session_factory):
    """Нові /times після /course зберігають кінець курсу; /course off прибирає його"""
    sf = pg_session_factory
    user_id, med_id = run(medication_with_times(sf, [time(8)]))
    run(set_end(sf, med_id, date(2026, 11, 30)))

    async def retime():
        async with sf() as s:
            await set_schedule(s, med_id, [time(9), time(21)], TODAY)

    run(retime())

    async def state():
        async with sf() as s:
            return await course_end(s, med_id), await describe_medications(s, user_id)

    end, lines = run(state())
    assert end == date(2026, 11, 30)
    assert lines == ["Сертралін, 50 мг (таблетка) – 09:00, 21:00, курс до 30.11"]

    run(set_end(sf, med_id, None))
    end, lines = run(state())
    assert end is None
    assert lines == ["Сертралін, 50 мг (таблетка) – 09:00, 21:00"]
