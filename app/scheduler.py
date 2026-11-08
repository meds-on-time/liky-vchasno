"""Process-lifecycle placeholder, NOT the medication reminder scheduler."""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def scheduler_loop() -> None:
    logger.info("Scheduler placeholder started (no reminders implemented yet)")
    while True:
        await asyncio.sleep(60)
