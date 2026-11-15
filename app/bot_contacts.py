"""SCRUM-14, SCRUM-15: bot commands for trusted contacts and consent.

This router must be included BEFORE app.bot.router in app/main.py,
otherwise the general /start handler catches the invite deep link first.
"""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.database import SessionLocal
from app.services.contacts import (
    ALREADY_LINKED,
    ALREADY_USED,
    INVITE_PREFIX,
    NOT_FOUND,
    OK,
    SELF,
    accept_invite,
    create_invite,
    set_consent,
)
from app.services.users import register_user

router = Router()

INVITE_TEXT = (
    "Надішліть це посилання людині, яка має отримувати сигнал, "
    "якщо ви пропустите прийом:\n{link}\n\n"
    "Посилання одноразове. Сигнал почне надходити, коли ви увімкнете згоду: /consent_on"
)
CONTACT_LINKED = (
    "Тепер ви довірена особа для {patient}. "
    "Якщо {patient} пропустить прийом і дасть згоду на сповіщення, я вам напишу."
)
PATIENT_LINKED = (
    "{contact} тепер ваша довірена особа. "
    "Щоб вона отримувала сигнал про пропуск, увімкніть згоду: /consent_on"
)
ACCEPT_ERRORS = {
    NOT_FOUND: "Посилання недійсне. Попросіть надіслати нове.",
    ALREADY_USED: "Це посилання вже використано. Попросіть надіслати нове.",
    SELF: "Це ваше власне посилання – надішліть його іншій людині.",
    ALREADY_LINKED: "Ви вже довірена особа для {patient}.",
}
NO_CONTACTS = "Спершу запросіть довірену особу: /invite"
CONSENT_ON = "Згоду увімкнено: довірена особа отримає сигнал, якщо ви пропустите прийом."
CONSENT_OFF = "Згоду вимкнено: довірена особа більше не отримуватиме сигнал про пропуск."


def invite_link(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start={INVITE_PREFIX}{code}"


@router.message(Command("invite"))
async def invite_command(message: Message) -> None:
    tg_user = message.from_user
    async with SessionLocal() as session:
        user, _ = await register_user(session, tg_user.id, tg_user.full_name)
        code = await create_invite(session, user.id)

    me = await message.bot.get_me()
    await message.answer(INVITE_TEXT.format(link=invite_link(me.username, code)))


@router.message(
    CommandStart(deep_link=True, magic=F.args.startswith(INVITE_PREFIX))
)
async def accept_invite_start(message: Message, command: CommandObject) -> None:
    """/start inv_<code> – the trusted contact opened the invite link."""
    code = command.args.removeprefix(INVITE_PREFIX)
    tg_user = message.from_user
    async with SessionLocal() as session:
        contact, _ = await register_user(session, tg_user.id, tg_user.full_name)
        result, patient = await accept_invite(session, code, contact.id)

    patient_name = (patient.name if patient else None) or "вашого близького"
    if result != OK:
        await message.answer(ACCEPT_ERRORS[result].format(patient=patient_name))
        return

    await message.answer(CONTACT_LINKED.format(patient=patient_name))
    await message.bot.send_message(
        patient.telegram_id,
        PATIENT_LINKED.format(contact=contact.name or "Довірена особа"),
    )


async def _consent(message: Message, value: bool) -> None:
    tg_user = message.from_user
    async with SessionLocal() as session:
        user, _ = await register_user(session, tg_user.id, tg_user.full_name)
        changed = await set_consent(session, user.id, value)

    if changed == 0:
        await message.answer(NO_CONTACTS)
    else:
        await message.answer(CONSENT_ON if value else CONSENT_OFF)


@router.message(Command("consent_on"))
async def consent_on_command(message: Message) -> None:
    await _consent(message, True)


@router.message(Command("consent_off"))
async def consent_off_command(message: Message) -> None:
    await _consent(message, False)
