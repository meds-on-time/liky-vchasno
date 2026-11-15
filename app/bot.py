"""Telegram bot handlers. Business logic lives in app/services."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.database import SessionLocal
from app.services.users import register_user

router = Router()

WELCOME_NEW = (
    "Вітаю, {name}! Це «Ліки вчасно» – я нагадуватиму про прийом ліків.\n"
    "Сервіс лише нагадує і не дає медичних порад."
)
WELCOME_BACK = "З поверненням, {name}! Ви вже зареєстровані."


@router.message(CommandStart())
async def start_command(message: Message) -> None:
    tg_user = message.from_user
    async with SessionLocal() as session:
        user, created = await register_user(session, tg_user.id, tg_user.full_name)

    text = WELCOME_NEW if created else WELCOME_BACK
    await message.answer(text.format(name=user.name or "друже"))