"""SCRUM-71 (tests for SCRUM-69/31): patients' schedules in the web cabinet on PostgreSQL.

A trusted contact logs in with a one-time token and calls GET /contacts/patients.
Data is created through the same services the bot uses (/add, /times, /course,
/invite, /consent_on), so the whole chain is checked on the real database.
"""

import asyncio
from datetime import UTC, date, datetime, time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Medication
from app.services import web_auth
from app.services.contacts import accept_invite, create_invite, set_consent
from app.services.courses import set_course_end
from app.services.schedules import set_schedule
from app.services.users import register_user

TODAY = date(2026, 11, 18)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def client(pg_session_factory):
    return TestClient(app)


async def user(sf, telegram_id, name) -> int:
    async with sf() as s:
        u, _ = await register_user(s, telegram_id, name)
        return u.id


async def medication(sf, user_id, name, dose, form=None, times=(), end=None) -> int:
    async with sf() as s:
        med = Medication(user_id=user_id, name=name, dose=dose, form=form)
        s.add(med)
        await s.commit()
        med_id = med.id
    if times:
        async with sf() as s:
            await set_schedule(s, med_id, list(times), TODAY)
    if end:
        async with sf() as s:
            await set_course_end(s, med_id, end)
    return med_id


async def link(sf, patient_id, contact_id, consent=True):
    async with sf() as s:
        code = await create_invite(s, patient_id)
        assert (await accept_invite(s, code, contact_id))[0] == "ok"
        await set_consent(s, patient_id, consent)


async def consent(sf, patient_id, value):
    async with sf() as s:
        await set_consent(s, patient_id, value)


async def login(sf, user_id) -> dict:
    """Header with a web session, as the cabinet gets it after POST /auth/exchange."""
    now = datetime.now(UTC)
    async with sf() as s:
        token = await web_auth.create_login_token(s, user_id, now)
    async with sf() as s:
        result = await web_auth.exchange_token(s, token, now)
    return {"Authorization": f"Bearer {result.session_token}"}


def test_contact_sees_patient_schedule_with_course_end(client, pg_session_factory):
    """Довірена особа зі згодою бачить препарати, дозу, форму, час (ГГ:ХХ) і кінець курсу"""
    sf = pg_session_factory
    olena = run(user(sf, 100, "Олена"))
    daughter = run(user(sf, 200, "Донька"))
    run(medication(sf, olena, "Сертралін", "50 мг", "таблетка",
                   times=[time(20), time(8)], end=date(2026, 11, 30)))
    run(medication(sf, olena, "Вітамін D", "1000 МО", times=[time(9)]))
    run(link(sf, olena, daughter))

    resp = client.get("/contacts/patients", headers=run(login(sf, daughter)))
    assert resp.status_code == 200
    [patient] = resp.json()["patients"]
    assert patient["name"] == "Олена"
    assert [
        (m["name"], m["dose"], m["form"], m["times"], m["end_date"])
        for m in patient["medications"]
    ] == [
        ("Сертралін", "50 мг", "таблетка", ["08:00", "20:00"], "2026-11-30"),
        ("Вітамін D", "1000 МО", None, ["09:00"], None),
    ]


def test_contact_sees_only_own_patients(client, pg_session_factory):
    """Двоє пацієнтів і двоє довірених осіб: кожна бачить лише тих, хто запросив саме її"""
    sf = pg_session_factory
    olena = run(user(sf, 100, "Олена"))
    petro = run(user(sf, 101, "Петро"))
    daughter = run(user(sf, 200, "Донька"))
    son = run(user(sf, 201, "Син"))
    run(medication(sf, olena, "Сертралін", "50 мг", times=[time(8)]))
    run(medication(sf, petro, "Метформін", "500 мг", times=[time(9)]))
    run(link(sf, olena, daughter))
    run(link(sf, petro, daughter))
    run(link(sf, petro, son))

    def names(contact):
        resp = client.get("/contacts/patients", headers=run(login(sf, contact)))
        return [p["name"] for p in resp.json()["patients"]]

    assert names(daughter) == ["Олена", "Петро"]
    assert names(son) == ["Петро"]
    assert names(olena) == []  # a patient sees nobody: nobody invited her


def test_consent_off_hides_patient_and_on_shows_again(client, pg_session_factory):
    """/consent_off ховає пацієнта з кабінету довіреної особи, /consent_on повертає"""
    sf = pg_session_factory
    olena = run(user(sf, 100, "Олена"))
    daughter = run(user(sf, 200, "Донька"))
    run(medication(sf, olena, "Сертралін", "50 мг", times=[time(8)]))
    run(link(sf, olena, daughter))
    headers = run(login(sf, daughter))

    assert len(client.get("/contacts/patients", headers=headers).json()["patients"]) == 1
    run(consent(sf, olena, False))
    assert client.get("/contacts/patients", headers=headers).json() == {"patients": []}
    run(consent(sf, olena, True))
    assert len(client.get("/contacts/patients", headers=headers).json()["patients"]) == 1


def test_invite_accepted_without_consent_is_hidden(client, pg_session_factory):
    """Запрошення прийняте, але згоду ще не дали → порожній список, а не дані пацієнта"""
    sf = pg_session_factory
    olena = run(user(sf, 100, "Олена"))
    daughter = run(user(sf, 200, "Донька"))
    run(medication(sf, olena, "Сертралін", "50 мг", times=[time(8)]))
    run(link(sf, olena, daughter, consent=False))
    resp = client.get("/contacts/patients", headers=run(login(sf, daughter)))
    assert resp.json() == {"patients": []}


def test_new_times_and_medication_without_schedule(client, pg_session_factory):
    """Нові /times одразу видно в кабінеті; препарат без розкладу – порожній список часу"""
    sf = pg_session_factory
    olena = run(user(sf, 100, "Олена"))
    daughter = run(user(sf, 200, "Донька"))
    med = run(medication(sf, olena, "Сертралін", "50 мг", times=[time(8)]))
    run(medication(sf, olena, "Омега-3", "1 капсула"))
    run(link(sf, olena, daughter))

    async def retime():
        async with sf() as s:
            await set_schedule(s, med, [time(10), time(22)], TODAY)

    run(retime())
    meds = client.get("/contacts/patients", headers=run(login(sf, daughter))).json()[
        "patients"][0]["medications"]
    assert [(m["name"], m["times"]) for m in meds] == [
        ("Сертралін", ["10:00", "22:00"]),
        ("Омега-3", []),
    ]


def test_patients_without_valid_session_is_401(client, pg_session_factory):
    """GET /contacts/patients без сесії або з вигаданою → 401"""
    assert client.get("/contacts/patients").status_code == 401
    bogus = client.get("/contacts/patients", headers={"Authorization": "Bearer nope"})
    assert bogus.status_code == 401
