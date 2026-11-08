"""Minimal Telegram bot placeholder; Telegram business logic belongs to the team."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def start_command(message: Message) -> None:
    await message.answer("Ліки вчасно: бот підключено. Функції нагадувань у розробці.")
