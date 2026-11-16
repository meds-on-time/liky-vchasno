"""SCRUM-40: bot side on PostgreSQL – scheduler -> deliver -> buttons -> answers.

Telegram is replaced by a fake bot that records send_message calls,
so the real handlers and services run against the real database.
"""

import asyncio
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import bot_reminders
from app.models import Medication, User
from app.notifications import deliver
from app.services import reminders
from app.services.contacts import accept_invite, create_invite, set_consent
from app.services.schedules import set_schedule
from app.services.users import register_user
from app.timeutils import KYIV, now_utc

PATIENT_TG = 100
STRANGER_TG = 999


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def sf(pg_session_factory, monkeypatch):
    """Button handlers open sessions via SessionLocal – point it to the test DB."""
    monkeypatch.setattr(bot_reminders, "SessionLocal", pg_session_factory)
    return pg_session_factory


def fake_bot():
    return SimpleNamespace(send_message=AsyncMock())


def fake_callback(data: str, user_id: int = PATIENT_TG):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=user_id),
        message=None,  # no old message to edit in tests
        answer=AsyncMock(),
    )


async def reminder_now(sf):
    """Medication scheduled at the current Kyiv minute; returns the scheduler output."""
    async with sf() as s:
        user = User(telegram_id=PATIENT_TG, name="Олена")
        s.add(user)
        await s.flush()
        med = Medication(user_id=user.id, name="Сертралін", dose="50 мг")
        s.add(med)
        await s.commit()
        now_kyiv = datetime.now(KYIV).replace(second=0, microsecond=0)
        await set_schedule(s, med.id, [now_kyiv.time()], now_kyiv.date())
    async with sf() as s:
        return await reminders.tick(s, now_utc())


def sent_texts(bot) -> list[str]:
    return [c.args[1] for c in bot.send_message.await_args_list]


def test_scheduler_delivers_reminder_with_two_buttons(sf):
    """Планувальник → deliver: пацієнт отримує текст з препаратом і кнопки taken/snooze"""
    notifications = run(reminder_now(sf))
    bot = fake_bot()
    run(deliver(bot, notifications))

    call = bot.send_message.await_args
    chat_id, text = call.args
    assert chat_id == PATIENT_TG
    assert "Сертралін, 50 мг" in text
    intake_id = notifications[0].intake.id
    buttons = [b.callback_data for row in call.kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == [f"taken:{intake_id}", f"snooze:{intake_id}"]


def test_take_button_twice_records_and_then_says_already(sf):
    """Кнопка «Прийняв» двічі: «Записано о …», потім «Вже відмічено о …»"""
    intake_id = run(reminder_now(sf))[0].intake.id
    bot = fake_bot()
    run(bot_reminders.on_take(fake_callback(f"taken:{intake_id}"), bot))
    run(bot_reminders.on_take(fake_callback(f"taken:{intake_id}"), bot))
    first, second = sent_texts(bot)
    assert first.startswith("Записано о ")
    assert second == first.replace("Записано", "Вже відмічено")


def test_snooze_button_answers_time_in_10_minutes(sf):
    """Кнопка «Нагадати за 10 хв»: відповідь «Нагадаю о ГГ:ХХ»"""
    intake_id = run(reminder_now(sf))[0].intake.id
    bot = fake_bot()
    run(bot_reminders.on_snooze(fake_callback(f"snooze:{intake_id}"), bot))
    [text] = sent_texts(bot)
    assert text.startswith("Нагадаю о ")


def test_other_user_cannot_press_patients_button(sf):
    """Чужий користувач натискає «Прийняв» – «Це не ваше нагадування», прийом не змінено"""
    intake_id = run(reminder_now(sf))[0].intake.id
    bot = fake_bot()
    callback = fake_callback(f"taken:{intake_id}", user_id=STRANGER_TG)
    run(bot_reminders.on_take(callback, bot))
    callback.answer.assert_awaited_once_with(bot_reminders.NOT_YOURS, show_alert=True)
    bot.send_message.assert_not_awaited()

    async def status():
        async with sf() as s:
            return (await reminders.take(s, intake_id, now_utc()))[0]

    assert run(status()) == "ok"  # still pending, so the owner can take it


def test_unknown_intake_button_says_not_found(sf):
    """Кнопка для неіснуючого прийому – відповідь «Прийом не знайдено»"""
    bot = fake_bot()
    run(bot_reminders.on_take(fake_callback("taken:999"), bot))
    assert sent_texts(bot) == [bot_reminders.NOT_FOUND]


def test_missed_alert_reaches_trusted_contact(sf):
    """Сигнал про пропуск: deliver надсилає довіреній особі ім'я, препарат і час"""
    day = date(2026, 11, 17)
    t = datetime.combine(day, time(20), tzinfo=KYIV)

    async def scenario():
        async with sf() as s:
            patient, _ = await register_user(s, PATIENT_TG, "Олена")
            contact, _ = await register_user(s, 200, "Донька")
            med = Medication(user_id=patient.id, name="Сертралін", dose="50 мг")
            s.add(med)
            await s.commit()
            await set_schedule(s, med.id, [time(20)], day)
            code = await create_invite(s, patient.id)
            await accept_invite(s, code, contact.id)
            await set_consent(s, patient.id, True)
        async with sf() as s:
            await reminders.tick(s, t)
        async with sf() as s:
            return await reminders.tick(s, t.replace(hour=21))

    notifications = run(scenario())
    bot = fake_bot()
    run(deliver(bot, notifications))
    chat_id, text = bot.send_message.await_args.args
    assert chat_id == 200
    assert "Олена" in text and "Сертралін, 50 мг" in text and "20:00" in text
