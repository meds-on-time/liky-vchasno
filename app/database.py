from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)

# Session = one unit of work with the DB (read, write, commit)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)