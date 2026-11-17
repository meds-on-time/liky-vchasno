"""SCRUM-19: course duration (N days)."""

import asyncio
from datetime import date, datetime, time

import pytest
from sqlalchemy import select

from app.models import Medication, Schedule, User
from app.services import reminders
from app.services.courses import (
    CourseError,
    course_end,
    course_end_date,
    parse_course_days,
    set_course_end,
)
from app.services.medications import describe_medications
from app.services.schedules import set_schedule
from app.timeutils import KYIV

TODAY = date(2026, 11, 17)


def run(coro):
    return asyncio.run(coro)


async def add_medication(session_factory, times=(time(8), time(20))) -> int:
    """Patient with one medication; times=None – no schedule yet."""
    async with session_factory() as s:
        user = User(telegram_id=100, name="Олена")
        s.add(user)
        await s.flush()
        med = Medication(user_id=user.id, name="Сертралін", dose="50 мг")
        s.add(med)
        await s.commit()
        med_id = med.id
    if times:
        async with session_factory() as s:
            await set_schedule(s, med_id, list(times), TODAY)
    return med_id


async def set_end(session_factory, med_id, end):
    async with session_factory() as s:
        await set_course_end(s, med_id, end)


async def end_of(session_factory, med_id):
    async with session_factory() as s:
        return await course_end(s, med_id)


async def schedule_rows(session_factory, med_id):
    async with session_factory() as s:
        return list(
            await s.scalars(select(Schedule).where(Schedule.medication_id == med_id))
        )


# --- parse_course_days: межі N і вимкнення ---


@pytest.mark.parametrize("raw, days", [("14", 14), ("1", 1), ("365", 365), (" 7 ", 7)])
def test_parse_valid_days(raw, days):
    """N від 1 до 365 приймається"""
    assert parse_course_days(raw) == days


@pytest.mark.parametrize("raw", ["0", "off", "OFF", "Off"])
def test_parse_off_means_no_end(raw):
    """/course 0 і /course off – курс без кінця"""
    assert parse_course_days(raw) is None


@pytest.mark.parametrize("raw", ["366", "1000"])
def test_parse_too_long_course_is_rejected(raw):
    """Більше 365 днів – пояснення користувачу"""
    with pytest.raises(CourseError, match="від 1 до 365"):
        parse_course_days(raw)


@pytest.mark.parametrize("raw", ["-3", "abc", "14 днів", "", None, "1.5"])
def test_parse_not_a_number_is_rejected(raw):
    """Не число – пояснення з прикладом"""
    with pytest.raises(CourseError, match="/course 14"):
        parse_course_days(raw)


# --- course_end_date: дата кінця ---


def test_end_date_counts_today_as_day_one():
    """14 днів з 17.11 – останній день 30.11"""
    assert course_end_date(TODAY, 14) == date(2026, 11, 30)


def test_one_day_course_ends_today():
    assert course_end_date(TODAY, 1) == TODAY


def test_end_date_crosses_year():
    assert course_end_date(date(2026, 12, 25), 10) == date(2027, 1, 3)


def test_no_days_means_no_end():
    assert course_end_date(TODAY, None) is None


# --- set_course_end / course_end ---


def test_set_course_end_for_all_active_times(session_factory):
    med_id = run(add_medication(session_factory))
    run(set_end(session_factory, med_id, date(2026, 11, 30)))
    rows = run(schedule_rows(session_factory, med_id))
    assert [r.end_date for r in rows] == [date(2026, 11, 30)] * 2
    assert run(end_of(session_factory, med_id)) == date(2026, 11, 30)


def test_course_off_clears_end(session_factory):
    med_id = run(add_medication(session_factory))
    run(set_end(session_factory, med_id, date(2026, 11, 30)))
    run(set_end(session_factory, med_id, None))
    assert run(end_of(session_factory, med_id)) is None


def test_course_needs_intake_times(session_factory):
    """Без розкладу курс задати не можна – бот просить спершу /times"""
    med_id = run(add_medication(session_factory, times=None))
    with pytest.raises(CourseError, match="/times"):
        run(set_end(session_factory, med_id, date(2026, 11, 30)))


def test_new_times_keep_course_end(session_factory):
    """/times після /course не скидає кінець курсу"""
    med_id = run(add_medication(session_factory))
    run(set_end(session_factory, med_id, date(2026, 11, 30)))

    async def change_times():
        async with session_factory() as s:
            return await set_schedule(s, med_id, [time(9)], TODAY)

    [new] = run(change_times())
    assert new.end_date == date(2026, 11, 30)
    assert run(end_of(session_factory, med_id)) == date(2026, 11, 30)


def test_meds_shows_course_end(session_factory):
    """/meds показує дату кінця курсу, якщо вона є"""
    med_id = run(add_medication(session_factory))

    async def describe():
        async with session_factory() as s:
            return await describe_medications(s, 1)

    assert run(describe()) == ["Сертралін, 50 мг – 08:00, 20:00"]
    run(set_end(session_factory, med_id, date(2026, 11, 30)))
    assert run(describe()) == ["Сертралін, 50 мг – 08:00, 20:00, курс до 30.11"]


# --- планувальник: останній день курсу ще нагадує, наступний – ні ---


async def tick(session_factory, day, hh):
    async with session_factory() as s:
        now = datetime.combine(day, time(hh), tzinfo=KYIV)
        return [n.kind for n in await reminders.tick(s, now)]


def test_reminder_on_last_day_of_course(session_factory):
    med_id = run(add_medication(session_factory, times=(time(20),)))
    run(set_end(session_factory, med_id, course_end_date(TODAY, 3)))  # до 19.11
    assert run(tick(session_factory, date(2026, 11, 19), 20)) == ["regular"]


def test_no_reminder_after_course(session_factory):
    med_id = run(add_medication(session_factory, times=(time(20),)))
    run(set_end(session_factory, med_id, course_end_date(TODAY, 3)))
    assert run(tick(session_factory, date(2026, 11, 20), 20)) == []
