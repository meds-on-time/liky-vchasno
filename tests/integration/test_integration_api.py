"""SCRUM-40: REST API through FastAPI TestClient on PostgreSQL.

take / snooze use the real current time inside the endpoint, so intakes are
created either by the scheduler tick for "now" or directly with a shifted T.
"""

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import INTAKE_PENDING, Intake, Medication, Schedule, User
from app.services import reminders
from app.services.schedules import set_schedule
from app.timeutils import KYIV, now_utc


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def client(pg_session_factory):
    return TestClient(app)


async def add_medication(sf, telegram_id=100) -> int:
    async with sf() as s:
        user = User(telegram_id=telegram_id, name="Олена")
        s.add(user)
        await s.flush()
        med = Medication(user_id=user.id, name="Сертралін", dose="50 мг")
        s.add(med)
        await s.commit()
        return med.id


async def intake_due_now(sf) -> int:
    """Schedule at the current Kyiv minute, then let the scheduler create the intake."""
    med_id = await add_medication(sf)
    now_kyiv = datetime.now(KYIV).replace(second=0, microsecond=0)
    async with sf() as s:
        await set_schedule(s, med_id, [now_kyiv.time()], now_kyiv.date())
    async with sf() as s:
        notifications = await reminders.tick(s, now_utc())
    assert [n.kind for n in notifications] == ["regular"]
    return notifications[0].intake.id


async def intake_started(sf, minutes_ago: int, telegram_id: int) -> int:
    """Pending intake whose time T was `minutes_ago` minutes before now."""
    med_id = await add_medication(sf, telegram_id)
    t = now_utc() - timedelta(minutes=minutes_ago)
    async with sf() as s:
        schedule = Schedule(medication_id=med_id, time_of_day=t.time(), start_date=t.date())
        s.add(schedule)
        await s.flush()
        intake = Intake(schedule_id=schedule.id, scheduled_at=t, status=INTAKE_PENDING)
        s.add(intake)
        await s.commit()
        return intake.id


def test_api_take_ok_then_already_taken(client, pg_session_factory):
    """POST /intakes/{id}/take: спершу ok, вдруге already_taken з тим самим часом"""
    intake_id = run(intake_due_now(pg_session_factory))
    first = client.post(f"/intakes/{intake_id}/take")
    assert first.status_code == 200
    assert first.json()["result"] == "ok"
    second = client.post(f"/intakes/{intake_id}/take")
    assert second.status_code == 200
    assert second.json() == {"result": "already_taken", "taken_at": first.json()["taken_at"]}


def test_api_snooze_after_take_is_already_taken(client, pg_session_factory):
    """POST /intakes/{id}/snooze після «Прийняв» → already_taken"""
    intake_id = run(intake_due_now(pg_session_factory))
    client.post(f"/intakes/{intake_id}/take")
    resp = client.post(f"/intakes/{intake_id}/snooze")
    assert resp.status_code == 200
    assert resp.json() == {"result": "already_taken", "remind_at": None}


def test_api_snooze_ok_gives_time_in_10_minutes(client, pg_session_factory):
    """POST /intakes/{id}/snooze до T+50 → ok і remind_at через 10 хв"""
    intake_id = run(intake_started(pg_session_factory, minutes_ago=5, telegram_id=101))
    before = now_utc()
    resp = client.post(f"/intakes/{intake_id}/snooze")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == "ok"
    remind_at = datetime.fromisoformat(body["remind_at"])
    assert timedelta(minutes=10) <= remind_at - before < timedelta(minutes=11)


def test_api_snooze_after_t_plus_50_is_too_late(client, pg_session_factory):
    """POST /intakes/{id}/snooze після T+50 → too_late"""
    intake_id = run(intake_started(pg_session_factory, minutes_ago=55, telegram_id=102))
    resp = client.post(f"/intakes/{intake_id}/snooze")
    assert resp.json() == {"result": "too_late", "remind_at": None}


def test_api_take_and_snooze_after_t_plus_60_are_missed(client, pg_session_factory):
    """POST take і snooze після T+60 → missed, статус не змінюється"""
    intake_id = run(intake_started(pg_session_factory, minutes_ago=61, telegram_id=103))
    assert client.post(f"/intakes/{intake_id}/take").json() == {
        "result": "missed", "taken_at": None
    }
    assert client.post(f"/intakes/{intake_id}/snooze").json() == {
        "result": "missed", "remind_at": None
    }


def test_api_unknown_intake_is_404(client, pg_session_factory):
    """POST /intakes/999/take і /snooze для неіснуючого прийому → 404"""
    assert client.post("/intakes/999/take").status_code == 404
    assert client.post("/intakes/999/snooze").status_code == 404


def test_api_put_and_get_schedule_same_times(client, pg_session_factory):
    """PUT /medications/{id}/schedule і GET повертають ті самі часи (відсортовані)"""
    med_id = run(add_medication(pg_session_factory))
    put = client.put(f"/medications/{med_id}/schedule", json={"times": ["20:00", "08:00"]})
    assert put.status_code == 200
    assert put.json()["times"] == ["08:00:00", "20:00:00"]
    get = client.get(f"/medications/{med_id}/schedule")
    assert get.status_code == 200
    assert get.json()["times"] == put.json()["times"]


def test_api_put_schedule_replaces_old_times(client, pg_session_factory):
    """Повторний PUT розкладу замінює старі часи, GET показує лише нові"""
    med_id = run(add_medication(pg_session_factory))
    client.put(f"/medications/{med_id}/schedule", json={"times": ["08:00", "20:00"]})
    client.put(f"/medications/{med_id}/schedule", json={"times": ["09:00"]})
    assert client.get(f"/medications/{med_id}/schedule").json()["times"] == ["09:00:00"]


def test_api_put_schedule_errors(client, pg_session_factory):
    """PUT розкладу: невідомий препарат → 404, некоректний час → 422"""
    med_id = run(add_medication(pg_session_factory))
    assert client.put("/medications/999/schedule", json={"times": ["08:00"]}).status_code == 404
    assert client.put(
        f"/medications/{med_id}/schedule", json={"times": ["25:00"]}
    ).status_code == 422
    assert client.put(f"/medications/{med_id}/schedule", json={"times": []}).status_code == 422
