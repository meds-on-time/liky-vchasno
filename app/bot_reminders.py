"""SCRUM-21/22/23: reminder buttons «Прийняв» and «Нагадати за 10 хв».

Handlers only parse the button, check the owner, call app/services/reminders
directly (bot and API run in one process, no HTTP needed) and answer.
"""

from contextlib import suppress
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from app.database import SessionLocal
from app.notifications import SNOOZE_PREFIX, TAKE_PREFIX, build_keyboard, kyiv_hhmm
from app.services import reminders
from app.services.intakes import owner_telegram_id
from app.timeutils import now_utc

reminders_router = Router(name="reminders")

NOT_FOUND = "Прийом не знайдено"
NOT_YOURS = "Це не ваше нагадування"
MISSED = "Час прийому минув, його позначено як пропущений"
TOO_LATE = "Відкласти вже не можна. Якщо прийняли ліки – натисніть «Прийняв»"
ALREADY_TAKEN_SNOOZE = "Ви вже відмітили цей прийом"


def parse_intake_id(data: str | None) -> int | None:
    """'taken:15' -> 15; anything malformed -> None."""
    if not data or ":" not in data:
        return None
    _, raw = data.split(":", 1)
    return int(raw) if raw.isdigit() else None


def format_take_answer(outcome: tuple[str, datetime | None] | None) -> str:
    if outcome is None:
        return NOT_FOUND
    result, at = outcome
    if result == "ok":
        return f"Записано о {kyiv_hhmm(at)}"
    if result == "already_taken":
        return f"Вже відмічено о {kyiv_hhmm(at)}"
    return MISSED


def format_snooze_answer(outcome: tuple[str, datetime | None] | None) -> str:
    if outcome is None:
        return NOT_FOUND
    result, at = outcome
    if result == "ok":
        return f"Нагадаю о {kyiv_hhmm(at)}"
    if result == "already_taken":
        return ALREADY_TAKEN_SNOOZE
    if result == "too_late":
        return TOO_LATE
    return MISSED


async def _run(callback: CallbackQuery, action):
    """Owner check + service call. Returns (allowed, outcome)."""
    intake_id = parse_intake_id(callback.data)
    if intake_id is None:
        return True, None
    async with SessionLocal() as session:
        owner = await owner_telegram_id(session, intake_id)
        if owner is None:
            return True, None
        if owner != callback.from_user.id:
            return False, None
        return True, await action(session, intake_id, now_utc())


async def _reply(callback: CallbackQuery, bot: Bot, text: str, keep_take_button: bool) -> None:
    """Update the old message's buttons, send the answer, stop the button spinner."""
    if isinstance(callback.message, Message):
        markup = None
        if keep_take_button:
            markup = build_keyboard(parse_intake_id(callback.data), show_snooze=False)
        # Ignore "message is not modified" and edits of very old messages
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=markup)
    await bot.send_message(callback.from_user.id, text)
    await callback.answer()


@reminders_router.callback_query(F.data.startswith(TAKE_PREFIX))
async def on_take(callback: CallbackQuery, bot: Bot) -> None:
    allowed, outcome = await _run(callback, reminders.take)
    if not allowed:
        await callback.answer(NOT_YOURS, show_alert=True)
        return
    await _reply(callback, bot, format_take_answer(outcome), keep_take_button=False)


@reminders_router.callback_query(F.data.startswith(SNOOZE_PREFIX))
async def on_snooze(callback: CallbackQuery, bot: Bot) -> None:
    allowed, outcome = await _run(callback, reminders.snooze)
    if not allowed:
        await callback.answer(NOT_YOURS, show_alert=True)
        return
    # After a successful snooze the user can still confirm from the same message
    snoozed = outcome is not None and outcome[0] == "ok"
    await _reply(callback, bot, format_snooze_answer(outcome), keep_take_button=snoozed)
