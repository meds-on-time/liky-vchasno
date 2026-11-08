"""SCRUM-13: user registration via /start."""

import asyncio

from sqlalchemy import func, select

from app.models import User
from app.services.users import register_user


def run(coro):
    return asyncio.run(coro)


def test_new_user_is_created(session_factory):
    async def scenario():
        async with session_factory() as session:
            return await register_user(session, 111, "Олена")

    user, created = run(scenario())
    assert created is True
    assert user.telegram_id == 111
    assert user.name == "Олена"


def test_repeated_start_does_not_create_duplicate(session_factory):
    async def scenario():
        async with session_factory() as session:
            first, _ = await register_user(session, 222, "Петро")
            second, created_again = await register_user(session, 222, "Петро")
            count = await session.scalar(select(func.count()).select_from(User))
            return first, second, created_again, count

    first, second, created_again, count = run(scenario())
    assert created_again is False
    assert first.id == second.id
    assert count == 1


def test_different_users_get_different_records(session_factory):
    async def scenario():
        async with session_factory() as session:
            a, _ = await register_user(session, 333, "Анна")
            b, _ = await register_user(session, 444, None)
            return a, b

    a, b = run(scenario())
    assert a.id != b.id
    assert b.name is None