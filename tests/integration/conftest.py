"""SCRUM-40: integration tests on a real PostgreSQL.

They run only when TEST_DATABASE_URL is set, e.g.
    postgresql+asyncpg://postgres:test@localhost:5433/test
Without it every test in this folder is skipped, so a plain `pytest` works anywhere.
Every test starts with empty tables (drop_all + create_all).
"""

import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import get_session
from app.main import app
from app.models import Base

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def pg_session_factory():
    """async_sessionmaker bound to the test PostgreSQL, also used by the API."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set: integration tests need PostgreSQL")

    # NullPool: every asyncio.run() gets its own connection (no cross-loop reuse)
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    async def reset_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(reset_tables())
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield factory
    app.dependency_overrides.pop(get_session, None)
    asyncio.run(engine.dispose())
