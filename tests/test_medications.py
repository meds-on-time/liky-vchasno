"""SCRUM-17: add a medication (service validation and bot helpers)."""

import asyncio
from datetime import date, time

import pytest
from sqlalchemy import func, select

from app.bot_medications import (
    CANCEL_DATA,
    FORM_PREFIX,
    build_form_keyboard,
    format_added,
    format_my_medications,
)
from app.models import Medication, User
from app.services.medications import (
    FORMS,
    MedicationError,
    add_medication,
    describe_medications,
    has_medication_named,
)
from app.services.schedules import latest_medication, set_schedule


def run(coro):
    return asyncio.run(coro)


async def make_user(sf, telegram_id=1) -> int:
    async with sf() as s:
        user = User(telegram_id=telegram_id, name="Test")
        s.add(user)
        await s.commit()
        return user.id


async def add(sf, user_id, name="Сертралін", dose="50 мг", form="таблетка"):
    async with sf() as s:
        return await add_medication(s, user_id, name, dose, form)


async def count_medications(sf) -> int:
    async with sf() as s:
        return await s.scalar(select(func.count()).select_from(Medication))


def test_add_medication_saves_name_dose_form(session_factory):
    """Препарат з коректними назвою, дозою і формою зберігається в БД"""
    user_id = run(make_user(session_factory))
    med = run(add(session_factory, user_id, "  Сертралін ", " 50 мг ", "Таблетка"))
    assert (med.user_id, med.name, med.dose, med.form) == (
        user_id, "Сертралін", "50 мг", "таблетка"
    )
    assert run(count_medications(session_factory)) == 1


def test_add_medication_without_form(session_factory):
    """Форма необов'язкова: препарат без форми теж зберігається"""
    user_id = run(make_user(session_factory))
    assert run(add(session_factory, user_id, form=None)).form is None


@pytest.mark.parametrize("name", ["", "   ", "А", " Б "])
def test_too_short_name_is_rejected(session_factory, name):
    """Назва коротша за 2 символи (після strip) – відмова, нічого не збережено"""
    user_id = run(make_user(session_factory))
    with pytest.raises(MedicationError, match="коротка"):
        run(add(session_factory, user_id, name=name))
    assert run(count_medications(session_factory)) == 0


def test_too_long_name_is_rejected(session_factory):
    """Назва довша за 100 символів – відмова"""
    user_id = run(make_user(session_factory))
    with pytest.raises(MedicationError, match="довга"):
        run(add(session_factory, user_id, name="А" * 101))


@pytest.mark.parametrize("dose", ["", "   ", None])
def test_empty_dose_is_rejected(session_factory, dose):
    """Порожня доза – відмова з підказкою"""
    user_id = run(make_user(session_factory))
    with pytest.raises(MedicationError, match="дозу"):
        run(add(session_factory, user_id, dose=dose))


def test_too_long_dose_is_rejected(session_factory):
    """Доза довша за 50 символів – відмова"""
    user_id = run(make_user(session_factory))
    with pytest.raises(MedicationError, match="Доза"):
        run(add(session_factory, user_id, dose="5" * 51))


def test_unknown_form_is_rejected(session_factory):
    """Форма не зі списку (таблетка, капсула, краплі, сироп, інше) – відмова"""
    user_id = run(make_user(session_factory))
    with pytest.raises(MedicationError, match="Оберіть форму"):
        run(add(session_factory, user_id, form="пігулка-жуйка"))
    assert run(count_medications(session_factory)) == 0


def test_latest_medication_returns_just_added(session_factory):
    """Після /add команда /times бере саме щойно доданий препарат"""
    user_id = run(make_user(session_factory))
    run(add(session_factory, user_id, name="Вітамін D"))
    new = run(add(session_factory, user_id, name="Сертралін"))

    async def latest():
        async with session_factory() as s:
            return await latest_medication(s, user_id)

    assert run(latest()).id == new.id


def test_form_keyboard_has_all_forms_and_cancel():
    """Клавіатура форм містить усі 5 форм і кнопку «Скасувати»"""
    buttons = [b for row in build_form_keyboard().inline_keyboard for b in row]
    data = [b.callback_data for b in buttons]
    assert data == [f"{FORM_PREFIX}{f}" for f in FORMS] + [CANCEL_DATA]
    assert buttons[-1].text == "Скасувати"


def test_added_text_mentions_medication_and_times_hint():
    """Відповідь після збереження: назва, доза, форма і підказка /times"""
    med = Medication(name="Сертралін", dose="50 мг", form="таблетка")
    assert format_added(med) == (
        "Додано: Сертралін, 50 мг (таблетка). "
        "Тепер задайте час прийомів: /times 08:00 20:00"
    )


def test_has_medication_named_ignores_case_and_spaces(session_factory):
    """Пошук дубліката назви не залежить від регістру й пробілів (кирилиця теж)"""
    user_id = run(make_user(session_factory))
    run(add(session_factory, user_id, name="Сертралін"))

    async def check(name, uid=user_id):
        async with session_factory() as s:
            return await has_medication_named(s, uid, name)

    assert run(check("  сЕРТРАЛІН "))
    assert not run(check("Вітамін D"))
    other = run(make_user(session_factory, telegram_id=2))
    assert not run(check("Сертралін", other))  # other user's list is separate


def test_describe_medications_lists_dose_form_and_times(session_factory):
    """«Мої препарати»: назва, доза, форма і час прийомів; без розкладу – «час не задано»"""
    user_id = run(make_user(session_factory))
    med = run(add(session_factory, user_id))
    run(add(session_factory, user_id, name="Вітамін D", dose="1000 МО", form=None))

    async def scenario():
        async with session_factory() as s:
            await set_schedule(s, med.id, [time(20), time(8)], date(2026, 11, 16))
            return await describe_medications(s, user_id)

    assert run(scenario()) == [
        "Сертралін, 50 мг (таблетка) – 08:00, 20:00",
        "Вітамін D, 1000 МО – час не задано",
    ]


def test_my_medications_text():
    """Текст /meds: нумерований список або підказка /add, якщо препаратів немає"""
    assert format_my_medications([]) == "Препаратів ще немає. Додайте перший: /add"
    assert format_my_medications(["А, 1 мг – 08:00", "Б, 2 мг – час не задано"]) == (
        "Мої препарати:\n1. А, 1 мг – 08:00\n2. Б, 2 мг – час не задано"
    )
