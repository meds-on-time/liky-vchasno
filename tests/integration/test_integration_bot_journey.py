"""SCRUM-71: the whole user journey through the real aiogram Dispatcher on PostgreSQL.

/start -> /add -> /times -> /course -> /meds -> /web -> the cabinet login API.
Telegram is replaced by a fake bot session that records outgoing messages.
"""

import asyncio
from datetime import datetime, timedelta
from itertools import count
from urllib.parse import parse_qs, urlparse

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fastapi.testclient import TestClient

from app import bot as main_bot
from app import bot_medications, bot_web, config
from app.bot import router
from app.bot_medications import medications_router
from app.bot_web import web_router
from app.main import app
from app.timeutils import KYIV

USER_ID = 100


class FakeSession(BaseSession):
    """Answers every Bot API call locally and records it."""

    def __init__(self):
        super().__init__()
        self.requests = []
        self._ids = count(1000)

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=next(self._ids), date=datetime.now(),
                chat=Chat(id=method.chat_id, type="private"), text=method.text,
            )
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - not used
        yield b""

    async def close(self):
        pass


class Chat_:
    def __init__(self):
        self.session = FakeSession()
        self.bot = Bot(token="42:TEST", session=self.session)
        self.dp = Dispatcher()
        for r in (router, medications_router, web_router):
            self.dp.include_router(r)
        self._ids = count(1)
        self.user = User(id=USER_ID, is_bot=False, first_name="Олена")
        self.chat = Chat(id=USER_ID, type="private")

    def _message(self, text):
        return Message(message_id=next(self._ids), date=datetime.now(), chat=self.chat,
                       from_user=self.user, text=text)

    def _feed(self, update) -> list[str]:
        start = len(self.session.requests)
        asyncio.run(self.dp.feed_update(self.bot, update))
        return [r.text for r in self.session.requests[start:] if isinstance(r, SendMessage)]

    def send(self, text) -> list[str]:
        return self._feed(Update(update_id=next(self._ids), message=self._message(text)))

    def press(self, data) -> list[str]:
        callback = CallbackQuery(id=str(next(self._ids)), from_user=self.user,
                                 chat_instance="ci", data=data, message=self._message("…"))
        return self._feed(Update(update_id=next(self._ids), callback_query=callback))


@pytest.fixture
def chat(pg_session_factory, monkeypatch):
    for module in (main_bot, bot_medications, bot_web):
        monkeypatch.setattr(module, "SessionLocal", pg_session_factory)
    monkeypatch.setattr(config, "WEB_URL", "https://cabinet.example")
    yield Chat_()
    for r in (router, medications_router, web_router):
        r._parent_router = None  # module routers can be attached to one Dispatcher at a time


def test_user_journey_from_start_to_web_cabinet(chat):
    """Повний шлях у боті на PostgreSQL: /start → /add → /times → /course 7 → /meds → /web → вхід у кабінет"""
    assert chat.send("/start")[0].startswith("Вітаю, Олена!")
    chat.send("/add")
    chat.send("Сертралін")
    chat.send("50 мг")
    assert chat.press("medform:таблетка")[0].startswith("Додано: Сертралін, 50 мг (таблетка)")
    assert chat.send("/times 08:00 20:00") == ["Сертралін: нагадуватиму щодня о 08:00, 20:00."]

    end = datetime.now(KYIV).date() + timedelta(days=6)
    assert chat.send("/course 7") == [f"Сертралін: курс до {end:%d.%m}."]
    assert chat.send("/meds") == [
        f"Мої препарати:\n1. Сертралін, 50 мг (таблетка) – 08:00, 20:00, курс до {end:%d.%m}"
    ]

    [web_text] = chat.send("/web")
    url = next(w for w in web_text.split() if w.startswith("https://cabinet.example/login"))
    token = parse_qs(urlparse(url).query)["token"][0]
    client = TestClient(app)
    exchanged = client.post("/auth/exchange", json={"token": token})
    assert exchanged.status_code == 200
    session = exchanged.json()["session"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {session}"})
    assert me.json()["name"] == "Олена"


def test_course_errors_in_bot(chat):
    """/course у боті: без препарату, без часу прийомів, N поза 1–365 і /course off"""
    assert chat.send("/course 7") == ["Спершу додайте препарат: /add"]
    chat.send("/add")
    chat.send("Вітамін D")
    chat.send("1000 МО")
    chat.press("medform:капсула")
    assert chat.send("/course 7") == ["Спершу задайте час прийомів: /times 08:00 20:00"]
    chat.send("/times 09:00")
    assert chat.send("/course 400") == ["Тривалість курсу – від 1 до 365 днів."]
    assert chat.send("/course off") == ["Вітамін D: курс без дати завершення."]
