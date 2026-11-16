"""SCRUM-53: /web – one-time link to the web cabinet."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app import config
from app.database import SessionLocal
from app.services.users import register_user
from app.services.web_auth import LOGIN_TOKEN_TTL, create_login_token, login_url
from app.timeutils import now_utc

web_router = Router()

WEB_LINK_TEXT = (
    "Посилання для входу у веб-кабінет:\n{url}\n\n"
    "Воно одноразове і діє {minutes} хвилин. Якщо не встигли – надішліть /web ще раз."
)


@web_router.message(Command("web"))
async def web_command(message: Message) -> None:
    tg_user = message.from_user
    async with SessionLocal() as session:
        user, _ = await register_user(session, tg_user.id, tg_user.full_name)
        token = await create_login_token(session, user.id, now_utc())

    minutes = int(LOGIN_TOKEN_TTL.total_seconds() // 60)
    await message.answer(
        WEB_LINK_TEXT.format(url=login_url(config.WEB_URL, token), minutes=minutes)
    )
