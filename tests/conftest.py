"""Shared test fixtures. Unit tests use in-memory SQLite (no Docker needed)."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base


@pytest.fixture
def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())
    yield async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(engine.dispose())