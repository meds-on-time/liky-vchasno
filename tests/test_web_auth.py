"""SCRUM-53: one-time web login token and sessions."""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config
from app.database import get_session
from app.main import app
from app.models import User, WebLoginToken
from app.services import web_auth

NOW = datetime(2026, 11, 18, 18, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


async def make_user(sf, telegram_id=100, name="Олена") -> int:
    async with sf() as s:
        user = User(telegram_id=telegram_id, name=name)
        s.add(user)
        await s.commit()
        return user.id


async def new_token(sf, user_id, now=NOW) -> str:
    async with sf() as s:
        return await web_auth.create_login_token(s, user_id, now)


async def exchange(sf, token, now):
    async with sf() as s:
        return await web_auth.exchange_token(s, token, now)


def test_login_url_format():
    assert web_auth.login_url("https://cab.example/", "abc") == "https://cab.example/login?token=abc"


def test_only_hash_is_stored(session_factory):
    user_id = run(make_user(session_factory))
    token = run(new_token(session_factory, user_id))

    async def stored():
        async with session_factory() as s:
            return (await s.scalars(select(WebLoginToken.token_hash))).one()

    assert run(stored()) == web_auth.hash_token(token)
    assert run(stored()) != token


def test_valid_token_gives_session(session_factory):
    user_id = run(make_user(session_factory))
    token = run(new_token(session_factory, user_id))
    result = run(exchange(session_factory, token, NOW + timedelta(minutes=9)))
    assert result.status == web_auth.TOKEN_OK
    assert result.user.id == user_id
    assert result.session_token


def test_expired_token_is_rejected(session_factory):
    user_id = run(make_user(session_factory))
    token = run(new_token(session_factory, user_id))
    result = run(exchange(session_factory, token, NOW + timedelta(minutes=10)))
    assert result.status == web_auth.TOKEN_EXPIRED


def test_second_exchange_is_rejected(session_factory):
    user_id = run(make_user(session_factory))
    token = run(new_token(session_factory, user_id))
    run(exchange(session_factory, token, NOW))
    assert run(exchange(session_factory, token, NOW)).status == web_auth.TOKEN_USED


def test_unknown_token_is_invalid(session_factory):
    assert run(exchange(session_factory, "nope", NOW)).status == web_auth.TOKEN_INVALID


def test_session_works_until_expiry(session_factory):
    user_id = run(make_user(session_factory))
    token = run(new_token(session_factory, user_id))
    session_token = run(exchange(session_factory, token, NOW)).session_token

    async def who(now):
        async with session_factory() as s:
            user = await web_auth.user_by_session(s, session_token, now)
            return user.id if user else None

    assert run(who(NOW + timedelta(days=6))) == user_id
    assert run(who(NOW + web_auth.SESSION_TTL)) is None


def test_api_exchange_and_me(session_factory):
    user_id = run(make_user(session_factory))

    async def override():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    try:
        client = TestClient(app)
        token = run(new_token(session_factory, user_id, datetime.now(UTC)))

        ok = client.post("/auth/exchange", json={"token": token})
        assert ok.status_code == 200
        session_token = ok.json()["session"]

        again = client.post("/auth/exchange", json={"token": token})
        assert again.status_code == 401
        assert again.json()["detail"]["code"] == "token_used"

        bad = client.post("/auth/exchange", json={"token": "nope"})
        assert bad.json()["detail"]["code"] == "token_invalid"

        me = client.get("/auth/me", headers={"Authorization": f"Bearer {session_token}"})
        assert me.json() == {"id": user_id, "name": "Олена"}
        assert client.get("/auth/me").status_code == 401
        assert client.get("/auth/me", headers={"Authorization": "Bearer x"}).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_api_web_link_needs_internal_token(session_factory, monkeypatch):
    run(make_user(session_factory, telegram_id=555))

    async def override():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    monkeypatch.setattr(config, "INTERNAL_API_TOKEN", "secret")
    monkeypatch.setattr(config, "WEB_URL", "https://cab.example")
    try:
        client = TestClient(app)
        body = {"telegram_id": 555}
        assert client.post("/auth/web-link", json=body).status_code == 403
        wrong = {"X-Internal-Token": "wrong"}
        assert client.post("/auth/web-link", json=body, headers=wrong).status_code == 403
        ok = client.post("/auth/web-link", json=body, headers={"X-Internal-Token": "secret"})
        assert ok.status_code == 200
        assert ok.json()["url"].startswith("https://cab.example/login?token=")
        missing = client.post(
            "/auth/web-link", json={"telegram_id": 1}, headers={"X-Internal-Token": "secret"}
        )
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
