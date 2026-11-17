"""Commands shown in the Telegram menu button."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Реєстрація"),
    BotCommand(command="add", description="Додати препарат"),
    BotCommand(command="meds", description="Мої препарати"),
    BotCommand(command="times", description="Час прийомів, напр. /times 08:00 20:00"),
    BotCommand(command="course", description="Тривалість курсу, напр. /course 14"),
    BotCommand(command="invite", description="Запросити довірену особу"),
    BotCommand(command="consent_on", description="Увімкнути сигнал довіреній особі"),
    BotCommand(command="consent_off", description="Вимкнути сигнал довіреній особі"),
    BotCommand(command="web", description="Увійти у веб-кабінет"),
    BotCommand(command="cancel", description="Скасувати поточну дію"),
]


async def set_commands(bot: Bot) -> None:
    """Show COMMANDS in the menu button; a Telegram error must not stop the app."""
    try:
        await bot.set_my_commands(COMMANDS)
    except TelegramAPIError:
        logger.warning("Could not set bot menu commands")
