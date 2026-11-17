"""SCRUM-71 (tests for SCRUM-53): web cabinet login on PostgreSQL.

Checks what SQLite unit tests cannot: two exchanges of one token at the same
moment, the unique hash constraint, timezone-aware expiry and the bot /web
link working end to end with the real API.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import bot_web, config
from app.main import app
from app.models import User, WebLoginToken, WebSession
from app.services import web_auth

NOW = datetime(2026, 11, 18, 18, 0, tzinfo=UTC)
INTERNAL = "internal-test-secret"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def client(pg_session_factory, monkeypatch):
    monkeypatch.setattr(config, "INTERNAL_API_TOKEN", INTERNAL)
    monkeypatch.setattr(config, "WEB_URL", "https://cabinet.example")
    return TestClient(app)


async def make_user(sf, telegram_id=100, name="Олена") -> int:
    async with sf() as s:
        user = User(telegram_id=telegram_id, name=name)
        s.add(user)
        await s.commit()
        return user.id


async def new_token(sf, user_id, now) -> str:
    async with sf() as s:
        return await web_auth.create_login_token(s, user_id, now)


async def exchange(sf, token, now):
    async with sf() as s:
        return await web_auth.exchange_token(s, token, now)


def token_from(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


def test_api_full_login_flow(client, pg_session_factory):
    """Веб-вхід через API: web-link → exchange → /auth/me з сесією повертає користувача"""
    run(make_user(pg_session_factory))
    link = client.post(
        "/auth/web-link", json={"telegram_id": 100}, headers={"X-Internal-Token": INTERNAL}
    )
    assert link.status_code == 200
    url = link.json()["url"]
    assert url.startswith("https://cabinet.example/login?token=")

    exchanged = client.post("/auth/exchange", json={"token": token_from(url)})
    assert exchanged.status_code == 200
    body = exchanged.json()
    assert body["user"]["name"] == "Олена"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['session']}"})
    assert me.status_code == 200
    assert me.json()["name"] == "Олена"


def test_api_second_exchange_is_401_token_used(client, pg_session_factory):
    """Те саме посилання вдруге → 401 token_used з підказкою взяти нове через /web"""
    user_id = run(make_user(pg_session_factory))
    token = run(new_token(pg_session_factory, user_id, datetime.now(UTC)))
    assert client.post("/auth/exchange", json={"token": token}).status_code == 200
    second = client.post("/auth/exchange", json={"token": token})
    assert second.status_code == 401
    assert second.json()["detail"]["code"] == "token_used"
    assert "/web" in second.json()["detail"]["message"]


def test_api_expired_and_unknown_tokens_are_401(client, pg_session_factory):
    """Прострочений токен → 401 token_expired, вигаданий → 401 token_invalid"""
    user_id = run(make_user(pg_session_factory))
    old = run(new_token(pg_session_factory, user_id, datetime.now(UTC) - timedelta(minutes=11)))
    expired = client.post("/auth/exchange", json={"token": old})
    assert expired.status_code == 401
    assert expired.json()["detail"]["code"] == "token_expired"
    unknown = client.post("/auth/exchange", json={"token": "not-a-real-token"})
    assert unknown.status_code == 401
    assert unknown.json()["detail"]["code"] == "token_invalid"


def test_api_me_without_valid_session_is_401(client, pg_session_factory):
    """/auth/me без заголовка, з вигаданою або простроченою сесією → 401"""
    user_id = run(make_user(pg_session_factory))
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401

    # a session that was valid a week ago has expired by now
    token = run(new_token(pg_session_factory, user_id, datetime.now(UTC) - timedelta(days=8)))
    result = run(exchange(pg_session_factory, token, datetime.now(UTC) - timedelta(days=8)))
    old_session = result.session_token
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {old_session}"})
    assert me.status_code == 401


def test_api_web_link_needs_internal_token(client, pg_session_factory):
    """POST /auth/web-link без або з неправильним X-Internal-Token → 403, невідомий користувач → 404"""
    run(make_user(pg_session_factory))
    assert client.post("/auth/web-link", json={"telegram_id": 100}).status_code == 403
    wrong = client.post(
        "/auth/web-link", json={"telegram_id": 100}, headers={"X-Internal-Token": "wrong"}
    )
    assert wrong.status_code == 403
    missing = client.post(
        "/auth/web-link", json={"telegram_id": 999}, headers={"X-Internal-Token": INTERNAL}
    )
    assert missing.status_code == 404


def test_two_simultaneous_exchanges_give_one_session(pg_session_factory):
    """Два одночасні обміни одного токена (подвійне натискання) → рівно одна сесія"""
    user_id = run(make_user(pg_session_factory))
    token = run(new_token(pg_session_factory, user_id, NOW))

    async def both():
        return await asyncio.gather(
            exchange(pg_session_factory, token, NOW + timedelta(seconds=5)),
            exchange(pg_session_factory, token, NOW + timedelta(seconds=5)),
        )

    results = run(both())
    assert sorted(r.status for r in results) == [web_auth.TOKEN_OK, web_auth.TOKEN_USED]

    async def sessions():
        async with pg_session_factory() as s:
            return await s.scalar(select(func.count()).select_from(WebSession))

    assert run(sessions()) == 1


def test_token_lifetime_boundary_in_postgres(pg_session_factory):
    """Токен із PostgreSQL (timestamptz) діє 9 хв 59 с і прострочений рівно на 10-й хвилині"""
    user_id = run(make_user(pg_session_factory))
    early = run(new_token(pg_session_factory, user_id, NOW))
    late = run(new_token(pg_session_factory, user_id, NOW))
    almost = NOW + web_auth.LOGIN_TOKEN_TTL - timedelta(seconds=1)
    assert run(exchange(pg_session_factory, early, almost)).status == web_auth.TOKEN_OK
    at_ttl = NOW + web_auth.LOGIN_TOKEN_TTL
    assert run(exchange(pg_session_factory, late, at_ttl)).status == web_auth.TOKEN_EXPIRED


def test_only_hashes_stored_and_hash_is_unique(pg_session_factory):
    """У БД немає сирого токена, лише SHA-256; повторний хеш відхиляє обмеження UNIQUE"""
    user_id = run(make_user(pg_session_factory))
    token = run(new_token(pg_session_factory, user_id, NOW))

    async def stored():
        async with pg_session_factory() as s:
            return list(await s.scalars(select(WebLoginToken.token_hash)))

    hashes = run(stored())
    assert hashes == [web_auth.hash_token(token)]
    assert token not in hashes

    async def duplicate():
        async with pg_session_factory() as s:
            s.add(WebLoginToken(user_id=user_id, token_hash=hashes[0], expires_at=NOW))
            await s.commit()

    with pytest.raises(IntegrityError):
        run(duplicate())


def test_bot_web_command_link_logs_in(client, pg_session_factory, monkeypatch):
    """Бот /web надсилає посилання, токен з якого через API дає сесію в кабінеті"""
    monkeypatch.setattr(bot_web, "SessionLocal", pg_session_factory)
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=100, full_name="Олена"), answer=AsyncMock()
    )
    run(bot_web.web_command(message))

    text = message.answer.await_args.args[0]
    assert "діє 10 хвилин" in text
    url = next(word for word in text.split() if word.startswith("https://cabinet.example"))
    exchanged = client.post("/auth/exchange", json={"token": token_from(url)})
    assert exchanged.status_code == 200
    assert exchanged.json()["user"]["name"] == "Олена"
