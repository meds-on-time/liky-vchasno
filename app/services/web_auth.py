"""SCRUM-53: one-time login token for the web cabinet and web sessions.

Flow: bot /web -> create_login_token -> link {WEB_URL}/login?token=...
-> the page calls POST /auth/exchange -> exchange_token -> session token.
Tokens are random; the DB keeps only their SHA-256 hash.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, WebLoginToken, WebSession
from app.timeutils import as_utc

LOGIN_TOKEN_TTL = timedelta(minutes=10)
SESSION_TTL = timedelta(days=7)

TOKEN_OK = "ok"
TOKEN_INVALID = "token_invalid"
TOKEN_EXPIRED = "token_expired"
TOKEN_USED = "token_used"


@dataclass
class ExchangeResult:
    status: str
    session_token: str | None = None
    expires_at: datetime | None = None
    user: User | None = None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login_url(web_url: str, token: str) -> str:
    return f"{web_url.rstrip('/')}/login?token={token}"


async def create_login_token(session: AsyncSession, user_id: int, now: datetime) -> str:
    """Create a one-time token valid for LOGIN_TOKEN_TTL; returns the raw token."""
    token = secrets.token_urlsafe(32)
    session.add(
        WebLoginToken(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=as_utc(now) + LOGIN_TOKEN_TTL,
        )
    )
    await session.commit()
    return token


async def exchange_token(session: AsyncSession, token: str, now: datetime) -> ExchangeResult:
    """Swap a login token for a session; a token works only once and only before expiry."""
    now = as_utc(now)
    row = await session.scalar(
        select(WebLoginToken).where(WebLoginToken.token_hash == hash_token(token))
    )
    if row is None:
        return ExchangeResult(TOKEN_INVALID)
    if row.used_at is not None:
        return ExchangeResult(TOKEN_USED)
    if now >= as_utc(row.expires_at):
        return ExchangeResult(TOKEN_EXPIRED)

    row.used_at = now
    session_token = secrets.token_urlsafe(32)
    expires_at = now + SESSION_TTL
    session.add(
        WebSession(
            user_id=row.user_id, token_hash=hash_token(session_token), expires_at=expires_at
        )
    )
    await session.commit()
    user = await session.get(User, row.user_id)
    return ExchangeResult(TOKEN_OK, session_token, expires_at, user)


async def user_by_session(
    session: AsyncSession, session_token: str, now: datetime
) -> User | None:
    """User of a valid (not expired) session, otherwise None."""
    row = await session.scalar(
        select(WebSession).where(WebSession.token_hash == hash_token(session_token))
    )
    if row is None or as_utc(now) >= as_utc(row.expires_at):
        return None
    return await session.get(User, row.user_id)