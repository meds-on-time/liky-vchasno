from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)

# Session = one unit of work with the DB (read, write, commit)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    """FastAPI dependency: one DB session per request."""
    async with SessionLocal() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]