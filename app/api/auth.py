"""SCRUM-53: web cabinet login (POST /auth/web-link, POST /auth/exchange, GET /auth/me)."""

import secrets
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select

from app import config
from app.database import SessionDep
from app.models import User
from app.services import web_auth
from app.timeutils import now_utc

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False, description="Session token from POST /auth/exchange")

ERROR_MESSAGES = {
    web_auth.TOKEN_INVALID: "Посилання недійсне. Візьміть нове в боті командою /web.",
    web_auth.TOKEN_EXPIRED: "Посилання прострочене. Візьміть нове в боті командою /web.",
    web_auth.TOKEN_USED: "Посилання вже використано. Візьміть нове в боті командою /web.",
}


class UserOut(BaseModel):
    id: int
    name: str | None


class WebLinkIn(BaseModel):
    telegram_id: int


class WebLinkOut(BaseModel):
    url: str


class ExchangeIn(BaseModel):
    token: str


class ExchangeOut(BaseModel):
    session: str
    expires_at: datetime
    user: UserOut

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session": "8sK2...Qw",
                    "expires_at": "2026-11-24T18:00:00Z",
                    "user": {"id": 1, "name": "Олена"},
                }
            ]
        }
    }


async def current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    """Dependency for endpoints of the web cabinet: 401 without a valid session."""
    user = None
    if credentials is not None:
        user = await web_auth.user_by_session(session, credentials.credentials, now_utc())
    if user is None:
        raise HTTPException(status_code=401, detail="Потрібен вхід у веб-кабінет.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


@router.post(
    "/web-link",
    response_model=WebLinkOut,
    summary="Створити одноразове посилання для входу",
    description=(
        "Службовий ендпоінт: повертає посилання {WEB_URL}/login?token=… для користувача "
        "з указаним telegram_id. Потрібен заголовок X-Internal-Token. Бот створює посилання "
        "напряму через сервіс (команда /web), тому зовні цей ендпоінт зазвичай не потрібен."
    ),
    responses={403: {"description": "Немає або неправильний X-Internal-Token"},
               404: {"description": "Користувача не знайдено"}},
)
async def web_link(
    body: WebLinkIn,
    session: SessionDep,
    x_internal_token: Annotated[str | None, Header()] = None,
) -> WebLinkOut:
    if not config.INTERNAL_API_TOKEN or not secrets.compare_digest(
        x_internal_token or "", config.INTERNAL_API_TOKEN
    ):
        raise HTTPException(status_code=403, detail="Forbidden")
    user = await session.scalar(select(User).where(User.telegram_id == body.telegram_id))
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    token = await web_auth.create_login_token(session, user.id, now_utc())
    return WebLinkOut(url=web_auth.login_url(config.WEB_URL, token))


@router.post(
    "/exchange",
    response_model=ExchangeOut,
    summary="Обміняти одноразовий токен на сесію",
    description=(
        "Сторінка входу кабінету надсилає токен з посилання. У відповідь – session, "
        "яка далі передається в заголовку Authorization: Bearer <session>. "
        "Токен діє 10 хвилин і лише один раз; сесія – 7 днів."
    ),
    responses={401: {"description": "Токен недійсний, прострочений або вже використаний. "
                                    "detail.code: token_invalid | token_expired | token_used"}},
)
async def exchange(body: ExchangeIn, session: SessionDep) -> ExchangeOut:
    result = await web_auth.exchange_token(session, body.token, now_utc())
    if result.status != web_auth.TOKEN_OK:
        raise HTTPException(
            status_code=401,
            detail={"code": result.status, "message": ERROR_MESSAGES[result.status]},
        )
    return ExchangeOut(
        session=result.session_token,
        expires_at=result.expires_at,
        user=UserOut(id=result.user.id, name=result.user.name),
    )


@router.get(
    "/me",
    response_model=UserOut,
    summary="Поточний користувач кабінету",
    responses={401: {"description": "Немає дійсної сесії"}},
)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(id=user.id, name=user.name)
