"""Scheduler loop (SCRUM-52): checks intakes every 30 seconds."""

import asyncio
import logging

from aiogram import Bot

from app.database import SessionLocal
from app.notifications import deliver
from app.services.reminders import tick
from app.timeutils import now_utc

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 30


async def scheduler_loop(bot: Bot | None) -> None:
    logger.info("Scheduler started")
    while True:
        try:
            async with SessionLocal() as session:
                notifications = await tick(session, now_utc())
            if bot is not None and notifications:
                await deliver(bot, notifications)
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(INTERVAL_SECONDS)