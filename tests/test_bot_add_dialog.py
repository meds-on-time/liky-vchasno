"""SCRUM-17: the /add dialog end to end through a real aiogram Dispatcher.

Telegram is replaced by a fake bot session that records outgoing requests,
so the real handlers, FSM states and services run (database: SQLite in memory).
"""

import asyncio
from datetime import datetime
from itertools import count

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from sqlalchemy import select

from app import bot as main_bot
from app import bot_medications
from app.bot import router
from app.bot_medications import medications_router
from app.models import Medication

USER_ID = 100


class FakeSession(BaseSession):
    """Bot session that answers every API call locally and records it."""

    def __init__(self):
        super().__init__()
        self.requests = []
        self._ids = count(1000)

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=next(self._ids),
                date=datetime.now(),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - not used
        yield b""

    async def close(self):
        pass


class Chatter:
    """Sends updates to the dispatcher and collects the bot's text answers."""

    def __init__(self):
        self.session = FakeSession()
        self.bot = Bot(token="42:TEST", session=self.session)
        self.dp = Dispatcher()
        self.dp.include_router(router)
        self.dp.include_router(medications_router)
        self._ids = count(1)
        self.user = User(id=USER_ID, is_bot=False, first_name="Олена")
        self.chat = Chat(id=USER_ID, type="private")

    def _message(self, text):
        return Message(
            message_id=next(self._ids), date=datetime.now(), chat=self.chat,
            from_user=self.user, text=text,
        )

    def send(self, text) -> list[str]:
        return self._feed(Update(update_id=next(self._ids), message=self._message(text)))

    def press(self, data) -> list[str]:
        callback = CallbackQuery(
            id=str(next(self._ids)), from_user=self.user, chat_instance="ci",
            data=data, message=self._message("…"),
        )
        return self._feed(Update(update_id=next(self._ids), callback_query=callback))

    def _feed(self, update) -> list[str]:
        start = len(self.session.requests)
        asyncio.run(self.dp.feed_update(self.bot, update))
        return [
            r.text for r in self.session.requests[start:] if isinstance(r, SendMessage)
        ]

    def last_keyboard_data(self) -> list[str]:
        sent = [r for r in self.session.requests if isinstance(r, SendMessage)]
        markup = sent[-1].reply_markup
        return [b.callback_data for row in markup.inline_keyboard for b in row]


@pytest.fixture
def chat(session_factory, monkeypatch):
    monkeypatch.setattr(bot_medications, "SessionLocal", session_factory)
    monkeypatch.setattr(main_bot, "SessionLocal", session_factory)
    yield Chatter()
    # module-level routers may be attached to one Dispatcher at a time
    for r in (router, medications_router):
        r._parent_router = None


def medications(session_factory) -> list[tuple]:
    async def load():
        async with session_factory() as s:
            rows = await s.scalars(select(Medication).order_by(Medication.id))
            return [(m.name, m.dose, m.form) for m in rows]

    return asyncio.run(load())


def test_add_dialog_full_flow_then_times(chat, session_factory):
    """Діалог /add у боті: назва → доза → кнопка форми → збережено, далі /times працює"""
    assert chat.send("/add") == ["Як називається препарат?"]
    assert chat.last_keyboard_data() == ["add:cancel"]
    assert chat.send("Сертралін") == ["Яка доза? (напр. 50 мг)"]
    assert chat.send("50 мг") == ["Яка форма?"]
    assert "medform:таблетка" in chat.last_keyboard_data()
    assert chat.press("medform:таблетка") == [
        "Додано: Сертралін, 50 мг (таблетка). Тепер задайте час прийомів: /times 08:00 20:00"
    ]
    assert medications(session_factory) == [("Сертралін", "50 мг", "таблетка")]
    assert chat.send("/times 08:00 20:00") == ["Сертралін: нагадуватиму щодня о 08:00, 20:00."]


def test_add_dialog_repeats_question_on_bad_input(chat, session_factory):
    """Некоректні дані в /add: бот пояснює помилку і повторює те саме питання"""
    chat.send("/add")
    [answer] = chat.send("А")
    assert "Назва занадто коротка" in answer and answer.endswith("Як називається препарат?")
    chat.send("Сертралін")
    [answer] = chat.send("5" * 51)
    assert "Доза занадто довга" in answer
    chat.send("50 мг")
    [answer] = chat.send("пігулка")
    assert "Оберіть форму зі списку" in answer
    assert chat.send("краплі")[0].startswith("Додано: Сертралін, 50 мг (краплі)")
    assert medications(session_factory) == [("Сертралін", "50 мг", "краплі")]


def test_add_dialog_cancel_button_and_command(chat, session_factory):
    """Кнопка «Скасувати» і /cancel зупиняють /add, нічого не зберігається"""
    chat.send("/add")
    chat.send("Сертралін")
    assert chat.press("add:cancel") == ["Додавання препарату скасовано."]
    assert chat.send("Вітамін D") == []  # dialog is over: plain text is ignored
    chat.send("/add")
    assert chat.send("/cancel") == ["Додавання препарату скасовано."]
    assert chat.send("/cancel") == ["Немає дії, яку можна скасувати."]
    assert medications(session_factory) == []


def test_add_dialog_warns_about_duplicate_name(chat, session_factory):
    """Препарат з такою назвою вже є: бот попереджає і питає, чи додати ще один"""
    chat.send("/add")
    chat.send("Сертралін")
    chat.send("50 мг")
    chat.press("medform:таблетка")

    chat.send("/add")
    assert chat.send("сертралін") == [
        "У вас уже є препарат «сертралін». Додати ще один з такою назвою?"
    ]
    assert chat.last_keyboard_data() == ["add:dup_yes", "add:cancel"]
    assert chat.press("add:dup_yes") == ["Яка доза? (напр. 50 мг)"]
    chat.send("100 мг")
    chat.press("medform:таблетка")
    assert len(medications(session_factory)) == 2

    chat.send("/add")
    chat.send("Сертралін")
    assert chat.press("add:cancel") == ["Додавання препарату скасовано."]
    assert len(medications(session_factory)) == 2


def test_meds_command_shows_my_medications(chat):
    """/meds показує «Мої препарати» з дозою, формою і часом прийомів"""
    assert chat.send("/meds") == ["Препаратів ще немає. Додайте перший: /add"]
    chat.send("/add")
    chat.send("Сертралін")
    chat.send("50 мг")
    chat.press("medform:таблетка")
    chat.send("/times 08:00 20:00")
    assert chat.send("/meds") == [
        "Мої препарати:\n1. Сертралін, 50 мг (таблетка) – 08:00, 20:00"
    ]


def test_times_without_medication_points_to_add(chat):
    """/times до додавання препарату підказує команду /add"""
    assert chat.send("/times 08:00") == ["Спершу додайте препарат: /add"]
