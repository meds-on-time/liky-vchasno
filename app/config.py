import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://meds_local:local_only_password@db:5432/meds_local",
)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Address of the web cabinet (Taras' React app); the bot's /web link points here
WEB_URL = os.getenv("WEB_URL", "http://localhost:5173")
# Shared secret for POST /auth/web-link; empty = the endpoint is disabled
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")
