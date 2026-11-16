"""SCRUM-21/22/23: reminder text, buttons and answers (no Telegram needed)."""

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace

from app import bot_reminders
from app.bot_reminders import format_snooze_answer, format_take_answer, parse_intake_id
from app.models import Intake, Medication, Schedule, User
from app.notifications import build_keyboard, build_reminder_text, can_snooze
from app.services.intakes import owner_telegram_id
from app.services.reminders import Notification
from app.timeutils import KYIV, as_utc

DAY = date(2026, 11, 16)
T = datetime.combine(DAY, time(20, 0), tzinfo=KYIV)  # 20:00 Kyiv = 18:00 UTC


def run(coro):
    return asyncio.run(coro)


def notification(kind="regular") -> Notification:
    intake = Intake(id=7, schedule_id=1, scheduled_at=as_utc(T))
    med = Medication(id=1, user_id=1, name="Сертралін", dose="50 мг")
    return Notification(kind, 100, intake, med)


def callback_data(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


# ---------- keyboard ----------


def test_keyboard_with_snooze_has_two_buttons():
    """Клавіатура з відкладенням має кнопки «Прийняв» та «Нагадати за 10 хв»"""
    markup = build_keyboard(7, show_snooze=True)
    assert callback_data(markup) == ["taken:7", "snooze:7"]
    texts = [b.text for row in markup.inline_keyboard for b in row]
    assert texts == ["Прийняв", "Нагадати за 10 хв"]


def test_keyboard_without_snooze_has_only_take():
    """Клавіатура без відкладення містить лише кнопку «Прийняв»"""
    assert callback_data(build_keyboard(7, show_snooze=False)) == ["taken:7"]


def test_snooze_button_hidden_from_t_plus_50():
    """Відкладення доступне на T+49 і стає недоступним починаючи з T+50"""
    assert can_snooze(T, T + timedelta(minutes=49)) is True
    assert can_snooze(T, T + timedelta(minutes=50)) is False


# ---------- reminder text ----------


def test_reminder_text_has_name_dose_and_kyiv_time():
    """Текст нагадування містить назву ліків, дозу та час прийому за Києвом"""
    text = build_reminder_text(notification())
    assert "Сертралін" in text
    assert "50 мг" in text
    assert "20:00" in text  # Kyiv time, not 18:00 UTC
    assert text.startswith("Час прийняти ліки")


def test_reminder_text_depends_on_kind():
    """Початок тексту нагадування залежить від типу: відкладене або повторне"""
    assert build_reminder_text(notification("snooze")).startswith("Нагадую ще раз, як ви просили")
    assert build_reminder_text(notification("repeat")).startswith("Нагадуємо ще раз")


def test_reminder_text_with_naive_utc_from_sqlite():
    """Наївний UTC-час із SQLite коректно переводиться у київський час у тексті"""
    n = notification()
    n.intake.scheduled_at = datetime(2026, 11, 16, 18, 0)  # naive UTC, as SQLite returns
    assert "20:00" in build_reminder_text(n)


# ---------- answers ----------

AT = datetime(2026, 11, 16, 18, 5, tzinfo=UTC)  # 20:05 Kyiv


def test_take_answers():
    """Форматування тексту відповіді на «Прийняв» для всіх результатів"""
    assert format_take_answer(None) == "Прийом не знайдено"
    assert format_take_answer(("ok", AT)) == "Записано о 20:05"
    assert format_take_answer(("already_taken", AT)) == "Вже відмічено о 20:05"
    assert format_take_answer(("missed", None)) == (
        "Час прийому минув, його позначено як пропущений"
    )


def test_snooze_answers():
    """Форматування тексту відповіді на відкладення для всіх результатів"""
    assert format_snooze_answer(None) == "Прийом не знайдено"
    assert format_snooze_answer(("ok", AT)) == "Нагадаю о 20:05"
    assert format_snooze_answer(("already_taken", None)) == "Ви вже відмітили цей прийом"
    assert format_snooze_answer(("missed", None)) == (
        "Час прийому минув, його позначено як пропущений"
    )
    assert format_snooze_answer(("too_late", None)) == (
        "Відкласти вже не можна. Якщо прийняли ліки – натисніть «Прийняв»"
    )


def test_parse_intake_id():
    """Розбір ID прийому з callback_data та повернення None для некоректних даних"""
    assert parse_intake_id("taken:15") == 15
    assert parse_intake_id("snooze:3") == 3
    assert parse_intake_id("taken:abc") is None
    assert parse_intake_id("taken") is None
    assert parse_intake_id(None) is None


# ---------- owner check and handlers (DB in memory, fake Telegram) ----------


async def make_intake(sf) -> int:
    """Patient (telegram_id=100) with one pending intake at 20:00."""
    async with sf() as s:
        user = User(telegram_id=100, name="Олена")
        s.add(user)
        await s.flush()
        med = Medication(user_id=user.id, name="Сертралін", dose="50 мг")
        s.add(med)
        await s.flush()
        schedule = Schedule(medication_id=med.id, time_of_day=time(20), start_date=DAY)
        s.add(schedule)
        await s.flush()
        intake = Intake(schedule_id=schedule.id, scheduled_at=as_utc(T), status="pending")
        s.add(intake)
        await s.commit()
        return intake.id


def test_owner_telegram_id(session_factory):
    """Визначення telegram_id власника прийому та повернення None для неіснуючого ID"""
    intake_id = run(make_intake(session_factory))

    async def lookup(i):
        async with session_factory() as s:
            return await owner_telegram_id(s, i)

    assert run(lookup(intake_id)) == 100
    assert run(lookup(999)) is None


class FakeCallback:
    """Just enough of aiogram's CallbackQuery for the handlers."""

    def __init__(self, data: str, user_id: int):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = None  # not a real Message: no keyboard edit
        self.sent: list[str] = []
        self.alerts: list[str] = []
        self.bot = SimpleNamespace(send_message=self._send)

    async def _send(self, chat_id, text, **kwargs):
        self.sent.append(text)

    async def answer(self, text=None, show_alert=False):
        if text:
            self.alerts.append(text)


def press(monkeypatch, sf, handler, data, user_id, now):
    monkeypatch.setattr(bot_reminders, "SessionLocal", sf)
    monkeypatch.setattr(bot_reminders, "now_utc", lambda: as_utc(now))
    cb = FakeCallback(data, user_id)
    run(handler(cb, cb.bot))
    return cb


def test_take_button_records_and_second_press_is_already_taken(session_factory, monkeypatch):
    """Натискання «Прийняв» фіксує прийом, а повторне повідомляє про вже відмічений"""
    i = run(make_intake(session_factory))
    now = T + timedelta(minutes=5)
    first = press(monkeypatch, session_factory, bot_reminders.on_take, f"taken:{i}", 100, now)
    second = press(monkeypatch, session_factory, bot_reminders.on_take, f"taken:{i}", 100, now)
    assert first.sent == ["Записано о 20:05"]
    assert second.sent == ["Вже відмічено о 20:05"]


def test_snooze_button_answers_with_remind_time(session_factory, monkeypatch):
    """Натискання «Нагадати за 10 хв» відповідає часом наступного нагадування"""
    i = run(make_intake(session_factory))
    cb = press(monkeypatch, session_factory, bot_reminders.on_snooze, f"snooze:{i}", 100,
               T + timedelta(minutes=5))
    assert cb.sent == ["Нагадаю о 20:15"]


def test_someone_else_cannot_press_the_button(session_factory, monkeypatch):
    """Сторонній користувач не може натиснути кнопку чужого нагадування"""
    i = run(make_intake(session_factory))
    cb = press(monkeypatch, session_factory, bot_reminders.on_take, f"taken:{i}", 555,
               T + timedelta(minutes=5))
    assert cb.alerts == ["Це не ваше нагадування"]
    assert cb.sent == []


def test_unknown_intake_is_not_found(session_factory, monkeypatch):
    """Натискання кнопки для неіснуючого прийому повертає «Прийом не знайдено»"""
    cb = press(monkeypatch, session_factory, bot_reminders.on_take, "taken:999", 100, T)
    assert cb.sent == ["Прийом не знайдено"]
