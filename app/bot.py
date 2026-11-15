"""Telegram bot handlers. Business logic lives in app/services."""

from datetime import datetime

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.database import SessionLocal
from app.services.schedules import (
    ScheduleError,
    latest_medication,
    parse_times,
    set_schedule,
)
from app.services.users import register_user
from app.timeutils import KYIV

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


@router.message(Command("times"))
async def times_command(message: Message, command: CommandObject) -> None:
    """/times 08:00 20:00 – set intake times for the last added medication."""
    if not command.args:
        await message.answer("Напишіть час прийомів, напр.: /times 08:00 20:00")
        return

    async with SessionLocal() as session:
        user, _ = await register_user(
            session, message.from_user.id, message.from_user.full_name
        )
        medication = await latest_medication(session, user.id)
        if medication is None:
            await message.answer("Спершу додайте препарат.")
            return
        try:
            times = parse_times(command.args.split())
            rows = await set_schedule(
                session, medication.id, times, datetime.now(KYIV).date()
            )
        except ScheduleError as exc:
            await message.answer(str(exc))
            return

    listed = ", ".join(r.time_of_day.strftime("%H:%M") for r in rows)
    await message.answer(f"{medication.name}: нагадуватиму щодня о {listed}.")