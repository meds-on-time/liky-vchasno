"""Bot messages sent by the scheduler.

Minimal version so the scheduler works end to end.
Taras replaces the texts and adds buttons in SCRUM-21 / SCRUM-26
(keep the function names: send_reminder, send_missed_alert).
"""

from aiogram import Bot

from app.services.reminders import Notification
from app.timeutils import KYIV, as_utc

TEXTS = {
    "regular": "Час прийняти {med}, {dose} ({time}).",
    "snooze": "Нагадую: {med}, {dose} ({time}).",
}


def _time(n: Notification) -> str:
    return as_utc(n.intake.scheduled_at).astimezone(KYIV).strftime("%H:%M")


async def send_reminder(bot: Bot, n: Notification) -> None:
    text = TEXTS[n.kind].format(med=n.medication.name, dose=n.medication.dose, time=_time(n))
    await bot.send_message(n.chat_id, text)


async def send_missed_alert(bot: Bot, n: Notification) -> None:
    who = n.patient_name or "Ваш підопічний"
    await bot.send_message(
        n.chat_id, f"{who} пропустив(-ла) прийом: {n.medication.name} о {_time(n)}."
    )


async def deliver(bot: Bot, notifications: list[Notification]) -> None:
    for n in notifications:
        if n.kind == "missed_alert":
            await send_missed_alert(bot, n)
        else:
            await send_reminder(bot, n)