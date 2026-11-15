"""SCRUM-18: intake times per day."""

import asyncio
from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.database import get_session
from app.main import app
from app.models import Medication, User
from app.services.schedules import (
    ScheduleError,
    parse_times,
    set_schedule,
    validate_times,
)


def run(coro):
    return asyncio.run(coro)


async def add_medication(session_factory) -> int:
    async with session_factory() as session:
        user = User(telegram_id=1, name="Test")
        session.add(user)
        await session.flush()
        med = Medication(user_id=user.id, name="Сертралін", dose="50 мг")
        session.add(med)
        await session.commit()
        return med.id


def test_parse_times():
    assert parse_times(["8:00", "20:30"]) == [time(8, 0), time(20, 30)]


def test_parse_times_rejects_bad_value():
    with pytest.raises(ScheduleError):
        parse_times(["25:00"])


def test_validate_sorts_times():
    assert validate_times([time(20), time(8)]) == [time(8), time(20)]


def test_validate_rejects_empty_duplicates_and_too_many():
    with pytest.raises(ScheduleError):
        validate_times([])
    with pytest.raises(ScheduleError):
        validate_times([time(8), time(8)])
    with pytest.raises(ScheduleError):
        validate_times([time(h) for h in range(7)])


def test_set_schedule_replaces_old_times(session_factory):
    async def scenario():
        med_id = await add_medication(session_factory)
        async with session_factory() as session:
            await set_schedule(session, med_id, [time(8), time(20)], date(2026, 11, 15))
            rows = await set_schedule(session, med_id, [time(9)], date(2026, 11, 15))
            return [r.time_of_day for r in rows]

    assert run(scenario()) == [time(9)]


def test_api_put_and_get_schedule(session_factory):
    med_id = run(add_medication(session_factory))

    async def override():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    try:
        client = TestClient(app)
        put = client.put(f"/medications/{med_id}/schedule", json={"times": ["20:00", "08:00"]})
        assert put.status_code == 200
        assert put.json()["times"] == ["08:00:00", "20:00:00"]
        get = client.get(f"/medications/{med_id}/schedule")
        assert get.json()["times"] == ["08:00:00", "20:00:00"]
        assert client.put("/medications/999/schedule", json={"times": ["08:00"]}).status_code == 404
    finally:
        app.dependency_overrides.clear()