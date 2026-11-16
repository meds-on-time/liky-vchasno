"""Patients' schedules for a trusted contact (GET /contacts/patients)."""

import asyncio
from datetime import UTC, date, datetime, time

from fastapi.testclient import TestClient

from app.database import get_session
from app.main import app
from app.models import Medication, Schedule, TrustedContact, User
from app.services import web_auth
from app.services.patients import patients_of


def run(coro):
    return asyncio.run(coro)


async def setup(sf):
    """Patient Олена (2 times, course end) linked to Донька; Петро is someone else's patient."""
    async with sf() as s:
        olena = User(telegram_id=1, name="Олена")
        daughter = User(telegram_id=2, name="Донька")
        petro = User(telegram_id=3, name="Петро")
        stranger = User(telegram_id=4, name="Чужий")
        s.add_all([olena, daughter, petro, stranger])
        await s.flush()
        med = Medication(user_id=olena.id, name="Сертралін", dose="50 мг", form="таблетка")
        other = Medication(user_id=petro.id, name="Аспірин", dose="100 мг")
        s.add_all([med, other])
        await s.flush()
        s.add_all([
            Schedule(medication_id=med.id, time_of_day=time(20), start_date=date(2026, 11, 1),
                     end_date=date(2026, 11, 30)),
            Schedule(medication_id=med.id, time_of_day=time(8), start_date=date(2026, 11, 1),
                     end_date=date(2026, 11, 30)),
            Schedule(medication_id=med.id, time_of_day=time(12), start_date=date(2026, 11, 1),
                     is_active=False),
            Schedule(medication_id=other.id, time_of_day=time(9), start_date=date(2026, 11, 1)),
            TrustedContact(patient_id=olena.id, contact_id=daughter.id, invite_code="a"),
            TrustedContact(patient_id=petro.id, contact_id=stranger.id, invite_code="b"),
            TrustedContact(patient_id=petro.id, contact_id=None, invite_code="c"),
        ])
        await s.commit()
        return daughter.id, stranger.id


def test_contact_sees_own_patient_with_times_and_course_end(session_factory):
    daughter_id, _ = run(setup(session_factory))

    async def scenario():
        async with session_factory() as s:
            return await patients_of(s, daughter_id)

    result = run(scenario())
    assert [p["name"] for p in result] == ["Олена"]
    med = result[0]["medications"][0]
    assert med["name"] == "Сертралін"
    assert med["times"] == ["08:00", "20:00"]  # inactive 12:00 is hidden
    assert med["end_date"] == date(2026, 11, 30)


def test_no_patients_gives_empty_list(session_factory):
    run(setup(session_factory))

    async def scenario():
        async with session_factory() as s:
            nobody = User(telegram_id=9, name="Ніхто")
            s.add(nobody)
            await s.commit()
            return await patients_of(s, nobody.id)

    assert run(scenario()) == []


def test_api_requires_session_and_hides_other_patients(session_factory):
    daughter_id, stranger_id = run(setup(session_factory))

    async def override():
        async with session_factory() as s:
            yield s

    async def session_for(user_id):
        async with session_factory() as s:
            token = await web_auth.create_login_token(s, user_id, datetime.now(UTC))
            res = await web_auth.exchange_token(s, token, datetime.now(UTC))
            return res.session_token

    app.dependency_overrides[get_session] = override
    try:
        client = TestClient(app)
        assert client.get("/contacts/patients").status_code == 401

        daughter = {"Authorization": f"Bearer {run(session_for(daughter_id))}"}
        body = client.get("/contacts/patients", headers=daughter).json()["patients"]
        assert [p["name"] for p in body] == ["Олена"]
        assert body[0]["medications"][0]["times"] == ["08:00", "20:00"]

        stranger = {"Authorization": f"Bearer {run(session_for(stranger_id))}"}
        resp = client.get("/contacts/patients", headers=stranger).json()
        names = [p["name"] for p in resp["patients"]]
        assert names == ["Петро"]
    finally:
        app.dependency_overrides.clear()
