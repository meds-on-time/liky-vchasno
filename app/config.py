import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://meds_local:local_only_password@db:5432/meds_local",
)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
