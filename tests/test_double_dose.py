"""SCRUM-27: double dose protection.

(a) two intakes of one medication must be at least 60 minutes apart;
(b) a second 'taken' returns already_taken and does not create a second record.
"""

import asyncio
from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import get_session
from app.main import app
from app.models import EventLog, Medication, Schedule, User
from app.services import reminders
from app.services.schedules import (
    ScheduleError,
    check_min_gap,
    parse_times,
    validate_times,
)
from app.timeutils import KYIV

DAY = date(2026, 11, 16)


def run(coro):
    return asyncio.run(coro)


def test_gap_59_minutes_is_rejected():
    """Два прийоми з інтервалом 59 хв – помилка з обома часами в тексті"""
    with pytest.raises(ScheduleError) as exc:
        check_min_gap([time(8, 0), time(8, 59)])
    assert str(exc.value) == "Між прийомами має бути щонайменше 60 хв: 08:00 і 08:59."


def test_gap_exactly_60_minutes_is_ok():
    """Інтервал рівно 60 хв – дозволено"""
    check_min_gap([time(8, 0), time(9, 0)])


def test_single_intake_is_ok():
    """Один прийом на день – перевірка інтервалу не заважає"""
    check_min_gap([time(20, 0)])


def test_three_intakes_with_one_close_pair_is_rejected():
    """3 прийоми, з яких два ближче 60 хв – помилка саме для цієї пари"""
    with pytest.raises(ScheduleError, match="14:00 і 14:30"):
        validate_times([time(20), time(8), time(14), time(14, 30)])


def test_midnight_gap_40_minutes_is_rejected():
    """Перехід через північ: 23:30 і 00:10 – це 40 хв, помилка"""
    with pytest.raises(ScheduleError, match="23:30 і 00:10"):
        validate_times([time(0, 10), time(23, 30)])


def test_midnight_gap_90_minutes_is_ok():
    """Перехід через північ: 23:00 і 00:30 – це 90 хв, дозволено"""
    assert validate_times([time(23, 0), time(0, 30)]) == [time(0, 30), time(23, 0)]


def test_bot_times_command_gets_error_text():
    """/times 08:00 08:30 у боті: parse_times + validate_times дають текст помилки"""
    with pytest.raises(ScheduleError) as exc:
        validate_times(parse_times(["08:00", "08:30"]))
    assert "щонайменше 60 хв" in str(exc.value)


async def add_medication(sf) -> int:
    async with sf() as s:
        user = User(telegram_id=1, name="Test")
        s.add(user)
        await s.flush()
        med = Medication(user_id=user.id, name="Сертралін", dose="50 мг")
        s.add(med)
        await s.commit()
        return med.id


def test_api_put_schedule_with_close_times_returns_422(session_factory):
    """PUT /medications/{id}/schedule з прийомами ближче 60 хв → 422 і текст помилки"""
    med_id = run(add_medication(session_factory))

    async def override():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    try:
        client = TestClient(app)
        resp = client.put(
            f"/medications/{med_id}/schedule", json={"times": ["20:00", "20:30"]}
        )
        assert resp.status_code == 422
        assert "щонайменше 60 хв" in resp.json()["detail"]
        assert client.get(f"/medications/{med_id}/schedule").json()["times"] == []
    finally:
        app.dependency_overrides.clear()


def test_second_take_creates_only_one_taken_event(session_factory):
    """Два натискання «Прийняв»: друге – already_taken, в event_log рівно одна подія taken"""

    async def scenario():
        async with session_factory() as s:
            user = User(telegram_id=100, name="Олена")
            s.add(user)
            await s.flush()
            med = Medication(user_id=user.id, name="Сертралін", dose="50 мг")
            s.add(med)
            await s.flush()
            s.add(Schedule(medication_id=med.id, time_of_day=time(20), start_date=DAY))
            await s.commit()
        t = datetime.combine(DAY, time(20), tzinfo=KYIV)
        async with session_factory() as s:
            [n] = await reminders.tick(s, t)
            intake_id = n.intake.id
        async with session_factory() as s:
            first = await reminders.take(s, intake_id, t.replace(minute=3))
        async with session_factory() as s:
            second = await reminders.take(s, intake_id, t.replace(minute=5))
        async with session_factory() as s:
            events = list(await s.scalars(select(EventLog.event)))
        return first[0], second[0], events

    first, second, events = run(scenario())
    assert (first, second) == ("ok", "already_taken")
    assert events.count("taken") == 1
