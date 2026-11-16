"""SCRUM-17: /add dialog – name -> dose -> form -> save.

Business logic and validation live in app/services/medications.py.
"""

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.database import SessionLocal
from app.models import Medication
from app.services.medications import (
    FORMS,
    MedicationError,
    add_medication,
    describe_medications,
    has_medication_named,
    validate_dose,
    validate_form,
    validate_name,
)
from app.services.users import register_user

medications_router = Router(name="medications")

CANCEL_DATA = "add:cancel"
FORM_PREFIX = "medform:"
DUPLICATE_YES_DATA = "add:dup_yes"

ASK_NAME = "Як називається препарат?"
ASK_DOSE = "Яка доза? (напр. 50 мг)"
ASK_FORM = "Яка форма?"
CANCELLED = "Додавання препарату скасовано."
NOTHING_TO_CANCEL = "Немає дії, яку можна скасувати."
NOT_A_COMMAND = "Зараз триває додавання препарату. Надішліть відповідь текстом або /cancel."
ADDED = "Додано: {name}, {dose}{form}. Тепер задайте час прийомів: /times 08:00 20:00"
DUPLICATE = "У вас уже є препарат «{name}». Додати ще один з такою назвою?"
MY_MEDS_EMPTY = "Препаратів ще немає. Додайте перший: /add"
MY_MEDS_HEADER = "Мої препарати:"


class AddMedication(StatesGroup):
    name = State()
    confirm_duplicate = State()
    dose = State()
    form = State()


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Скасувати", callback_data=CANCEL_DATA)]]
    )


def build_duplicate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Так, додати", callback_data=DUPLICATE_YES_DATA)],
            [InlineKeyboardButton(text="Скасувати", callback_data=CANCEL_DATA)],
        ]
    )


def format_my_medications(lines: list[str]) -> str:
    if not lines:
        return MY_MEDS_EMPTY
    numbered = [f"{i}. {line}" for i, line in enumerate(lines, 1)]
    return "\n".join([MY_MEDS_HEADER, *numbered])


def build_form_keyboard() -> InlineKeyboardMarkup:
    """One button per form (two per row) and 'Cancel' in the last row."""
    buttons = [
        InlineKeyboardButton(text=form.capitalize(), callback_data=f"{FORM_PREFIX}{form}")
        for form in FORMS
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="Скасувати", callback_data=CANCEL_DATA)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_added(medication: Medication) -> str:
    form = f" ({medication.form})" if medication.form else ""
    return ADDED.format(name=medication.name, dose=medication.dose, form=form)


def _is_command(message: Message) -> bool:
    return bool(message.text) and message.text.startswith("/")


@medications_router.message(Command("add"))
async def add_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddMedication.name)
    await message.answer(ASK_NAME, reply_markup=build_cancel_keyboard())


@medications_router.message(Command("meds"))
async def meds_command(message: Message) -> None:
    """'My medications': name, dose, form and intake times."""
    async with SessionLocal() as session:
        user, _ = await register_user(
            session, message.from_user.id, message.from_user.full_name
        )
        lines = await describe_medications(session, user.id)
    await message.answer(format_my_medications(lines))


@medications_router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer(NOTHING_TO_CANCEL)
        return
    await state.clear()
    await message.answer(CANCELLED)


@medications_router.callback_query(F.data == CANCEL_DATA)
async def cancel_button(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(CANCELLED)
    await callback.answer()


@medications_router.message(StateFilter(AddMedication.name))
async def name_step(message: Message, state: FSMContext) -> None:
    if _is_command(message):
        await message.answer(NOT_A_COMMAND)
        return
    try:
        name = validate_name(message.text)
    except MedicationError as exc:
        await message.answer(f"{exc}\n{ASK_NAME}", reply_markup=build_cancel_keyboard())
        return
    await state.update_data(name=name)
    async with SessionLocal() as session:
        user, _ = await register_user(
            session, message.from_user.id, message.from_user.full_name
        )
        duplicate = await has_medication_named(session, user.id, name)
    if duplicate:
        await state.set_state(AddMedication.confirm_duplicate)
        await message.answer(DUPLICATE.format(name=name), reply_markup=build_duplicate_keyboard())
        return
    await state.set_state(AddMedication.dose)
    await message.answer(ASK_DOSE, reply_markup=build_cancel_keyboard())


@medications_router.callback_query(
    StateFilter(AddMedication.confirm_duplicate), F.data == DUPLICATE_YES_DATA
)
async def duplicate_yes(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddMedication.dose)
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(ASK_DOSE, reply_markup=build_cancel_keyboard())
    await callback.answer()


@medications_router.message(StateFilter(AddMedication.confirm_duplicate))
async def duplicate_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer(
        DUPLICATE.format(name=data.get("name")), reply_markup=build_duplicate_keyboard()
    )


@medications_router.message(StateFilter(AddMedication.dose))
async def dose_step(message: Message, state: FSMContext) -> None:
    if _is_command(message):
        await message.answer(NOT_A_COMMAND)
        return
    try:
        dose = validate_dose(message.text)
    except MedicationError as exc:
        await message.answer(f"{exc}\n{ASK_DOSE}", reply_markup=build_cancel_keyboard())
        return
    await state.update_data(dose=dose)
    await state.set_state(AddMedication.form)
    await message.answer(ASK_FORM, reply_markup=build_form_keyboard())


async def _save(state: FSMContext, tg_user, form: str) -> str:
    """Save the medication from the dialog data; returns the answer text."""
    data = await state.get_data()
    async with SessionLocal() as session:
        user, _ = await register_user(session, tg_user.id, tg_user.full_name)
        medication = await add_medication(
            session, user.id, data.get("name"), data.get("dose"), form
        )
    await state.clear()
    return format_added(medication)


@medications_router.callback_query(
    StateFilter(AddMedication.form), F.data.startswith(FORM_PREFIX)
)
async def form_button(callback: CallbackQuery, state: FSMContext) -> None:
    form = callback.data.removeprefix(FORM_PREFIX)
    try:
        text = await _save(state, callback.from_user, form)
    except MedicationError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(text)
    await callback.answer()


@medications_router.message(StateFilter(AddMedication.form))
async def form_text(message: Message, state: FSMContext) -> None:
    """The form can also be typed instead of pressing a button."""
    try:
        form = validate_form(message.text or "")
        text = await _save(state, message.from_user, form)
    except MedicationError as exc:
        await message.answer(f"{exc}\n{ASK_FORM}", reply_markup=build_form_keyboard())
        return
    await message.answer(text)
