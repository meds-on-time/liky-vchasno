
"""One application process: FastAPI + aiogram + scheduler."""

import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.api import intakes, schedules
from app.bot import router
from app.bot_commands import set_commands
from app.bot_contacts import router as contacts_router
from app.bot_medications import medications_router
from app.bot_reminders import reminders_router
from app.config import BOT_TOKEN
from app.database import engine
from app.scheduler import scheduler_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task] = []
    bot: Bot | None = None
    app.state.bot_enabled = False

    if BOT_TOKEN:
        bot = Bot(token=BOT_TOKEN)
        await set_commands(bot)
        dp = Dispatcher()
        dp.include_router(contacts_router)
        dp.include_router(router)
        dp.include_router(medications_router)
        dp.include_router(reminders_router)
        tasks.append(
            asyncio.create_task(
                dp.start_polling(bot, handle_signals=False, close_bot_session=False)
            )
        )
        app.state.bot_enabled = True
        logger.info("Telegram polling task started")
    else:
        logger.warning("BOT_TOKEN is empty; Telegram polling is disabled")

    tasks.append(asyncio.create_task(scheduler_loop(bot)))

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if bot is not None:
            await bot.session.close()
        await engine.dispose()


tags_metadata = [
    {
        "name": "intakes",
        "description": (
            "Операції з прийомами ліків: підтвердження прийому "
            "та відкладання нагадування."
        ),
    },
    {
        "name": "schedules",
        "description": (
            "Створення, оновлення та перегляд розкладу прийому препаратів."
        ),
    },
    {
        "name": "system",
        "description": "Службові ендпоінти для перевірки стану застосунку.",
    },
]


app = FastAPI(
    title="Ліки вчасно API",
    description=(
        "REST API навчального сервісу «Ліки вчасно». "
        "Система допомагає користувачам дотримуватися розкладу "
        "прийому препаратів через Telegram-бота. "
        "API забезпечує керування розкладом, підтвердження "
        "прийому ліків і відкладання нагадувань. "
        "Час прийомів відображається за часовим поясом Europe/Kyiv."
    ),
    version="0.1.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.include_router(intakes.router)
app.include_router(schedules.router)


@app.get(
    "/",
    tags=["system"],
    summary="Інформація про сервіс",
    description="Повертає назву сервісу та поточний статус стартового API.",
    responses={
        200: {
            "description": "Інформацію про сервіс отримано успішно."
        }
    },
)
async def root():
    return {"service": "Ліки вчасно", "status": "starter"}


@app.get(
    "/health",
    tags=["system"],
    summary="Перевірка стану сервера",
    description=(
        "Перевіряє доступність PostgreSQL та повертає інформацію "
        "про активність Telegram-бота."
    ),
    responses={
        200: {
            "description": "Сервер і база даних працюють.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "database": "connected",
                        "bot_enabled": True,
                    }
                }
            },
        },
        503: {
            "description": "База даних недоступна."
        },
    },
)
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=503,
            detail="database unavailable",
        ) from exc

    return {
        "status": "ok",
        "database": "connected",
        "bot_enabled": app.state.bot_enabled,
    }
