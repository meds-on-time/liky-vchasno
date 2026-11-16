"""SCRUM-17: add a medication (name, dose, form)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Medication

NAME_MIN = 2
NAME_MAX = 100
DOSE_MAX = 50
FORMS = ("таблетка", "капсула", "краплі", "сироп", "інше")


class MedicationError(ValueError):
    """Invalid medication data; the message is shown to the user."""


def validate_name(name: str | None) -> str:
    name = (name or "").strip()
    if len(name) < NAME_MIN:
        raise MedicationError(f"Назва занадто коротка: щонайменше {NAME_MIN} символи.")
    if len(name) > NAME_MAX:
        raise MedicationError(f"Назва занадто довга: не більше {NAME_MAX} символів.")
    return name


def validate_dose(dose: str | None) -> str:
    dose = (dose or "").strip()
    if not dose:
        raise MedicationError("Вкажіть дозу, напр. 50 мг.")
    if len(dose) > DOSE_MAX:
        raise MedicationError(f"Доза занадто довга: не більше {DOSE_MAX} символів.")
    return dose


def validate_form(form: str | None) -> str | None:
    if form is None:
        return None
    form = form.strip().lower()
    if form not in FORMS:
        raise MedicationError("Оберіть форму зі списку: " + ", ".join(FORMS) + ".")
    return form


async def add_medication(
    session: AsyncSession, user_id: int, name: str, dose: str, form: str | None
) -> Medication:
    """Validate and save a medication for the user."""
    medication = Medication(
        user_id=user_id,
        name=validate_name(name),
        dose=validate_dose(dose),
        form=validate_form(form),
    )
    session.add(medication)
    await session.commit()
    await session.refresh(medication)
    return medication
