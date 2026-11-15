"""Bot messages sent by the scheduler (SCRUM-21, SCRUM-26).

The scheduler calls deliver(bot, notifications): keep the names and
parameters of send_reminder, send_missed_alert and deliver.
Texts and keyboards are built by plain functions so they can be tested
without Telegram.
"""

from datetime import datetime

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.reminders import SNOOZE_DEADLINE, Notification
from app.timeutils import KYIV, as_utc, now_utc

TAKE_BUTTON = "Прийняв"
SNOOZE_BUTTON = "Нагадати за 10 хв"

TAKE_PREFIX = "taken:"
SNOOZE_PREFIX = "snooze:"

# First line of the reminder, by Notification.kind
REMINDER_HEADERS = {
    "regular": "Час прийняти ліки",
    "snooze": "Нагадую ще раз, як ви просили",
    "repeat": "Нагадуємо ще раз",  # SCRUM-25 (T+30), sent by the scheduler later
}


def kyiv_hhmm(dt: datetime) -> str:
    """HH:MM in Kyiv time (the DB stores UTC; SQLite returns naive values)."""
    return as_utc(dt).astimezone(KYIV).strftime("%H:%M")


def can_snooze(scheduled_at: datetime, now: datetime) -> bool:
    """Snooze is allowed only before T+50 (see app/services/reminders.py)."""
    return as_utc(now) < as_utc(scheduled_at) + SNOOZE_DEADLINE


def build_reminder_text(n: Notification) -> str:
    header = REMINDER_HEADERS.get(n.kind, REMINDER_HEADERS["regular"])
    return (
        f"{header}\n"
        f"{n.medication.name}, {n.medication.dose}\n"
        f"Час прийому: {kyiv_hhmm(n.intake.scheduled_at)}"
    )


def build_keyboard(intake_id: int, show_snooze: bool) -> InlineKeyboardMarkup:
    """One button per row: large buttons are easier to press for older users."""
    rows = [[InlineKeyboardButton(text=TAKE_BUTTON, callback_data=f"{TAKE_PREFIX}{intake_id}")]]
    if show_snooze:
        rows.append(
            [InlineKeyboardButton(text=SNOOZE_BUTTON, callback_data=f"{SNOOZE_PREFIX}{intake_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_reminder(bot: Bot, n: Notification) -> None:
    keyboard = build_keyboard(n.intake.id, can_snooze(n.intake.scheduled_at, now_utc()))
    await bot.send_message(n.chat_id, build_reminder_text(n), reply_markup=keyboard)


async def send_missed_alert(bot: Bot, n: Notification) -> None:
    who = n.patient_name or "Ваш підопічний"
    await bot.send_message(
        n.chat_id,
        f"{who} пропустив(-ла) прийом: {n.medication.name} о {kyiv_hhmm(n.intake.scheduled_at)}.",
    )


async def deliver(bot: Bot, notifications: list[Notification]) -> None:
    for n in notifications:
        if n.kind == "missed_alert":
            await send_missed_alert(bot, n)
        else:
            await send_reminder(bot, n)
