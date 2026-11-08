from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def register_user(
    session: AsyncSession, telegram_id: int, name: str | None
) -> tuple[User, bool]:
    """Return the existing user or create a new one.

    The bool is True if the user was created now (so repeated /start makes no duplicate).
    """
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is not None:
        return user, False

    user = User(telegram_id=telegram_id, name=name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, True