"""One application process: FastAPI + aiogram + scheduler placeholder."""

import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.bot import router
from app.config import BOT_TOKEN
from app.database import engine
from app.scheduler import scheduler_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task] = [asyncio.create_task(scheduler_loop())]
    bot: Bot | None = None
    app.state.bot_enabled = False

    if BOT_TOKEN:
        bot = Bot(token=BOT_TOKEN)
        dp = Dispatcher()
        dp.include_router(router)
        tasks.append(
            asyncio.create_task(
                dp.start_polling(bot, handle_signals=False, close_bot_session=False)
            )
        )
        app.state.bot_enabled = True
        logger.info("Telegram polling task started")
    else:
        logger.warning("BOT_TOKEN is empty; Telegram polling is disabled")

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if bot is not None:
            await bot.session.close()
        await engine.dispose()


app = FastAPI(title="Ліки вчасно API", version="0.1.0", lifespan=lifespan)


@app.get("/")
async def root():
    return {"service": "Ліки вчасно", "status": "starter"}


@app.get("/health")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "connected", "bot_enabled": app.state.bot_enabled}
