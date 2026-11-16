"""Schedules of the patients a trusted contact is linked to (web cabinet, SCRUM-31)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Medication, Schedule, TrustedContact, User


async def patients_of(session: AsyncSession, contact_user_id: int) -> list[dict]:
    """Patients who invited this user, with active medications and intake times.

    Only accepted invites (contact_id = this user) with consent on are returned:
    nobody sees other people's patients, and /consent_off hides the schedule too.
    """
    patients = await session.scalars(
        select(User)
        .join(TrustedContact, TrustedContact.patient_id == User.id)
        .where(
            TrustedContact.contact_id == contact_user_id,
            TrustedContact.consent.is_(True),
        )
        .order_by(User.id)
        .distinct()
    )
    result = []
    for patient in patients:
        medications = await session.scalars(
            select(Medication).where(Medication.user_id == patient.id).order_by(Medication.id)
        )
        meds = []
        for med in medications:
            rows = list(
                await session.scalars(
                    select(Schedule)
                    .where(Schedule.medication_id == med.id, Schedule.is_active.is_(True))
                    .order_by(Schedule.time_of_day)
                )
            )
            meds.append(
                {
                    "id": med.id,
                    "name": med.name,
                    "dose": med.dose,
                    "form": med.form,
                    "times": [r.time_of_day.strftime("%H:%M") for r in rows],
                    "end_date": _end_date(rows),
                }
            )
        result.append({"id": patient.id, "name": patient.name, "medications": meds})
    return result


def _end_date(rows: list[Schedule]) -> date | None:
    """Course end of a medication: latest end_date of its times, None if open-ended."""
    if not rows or any(r.end_date is None for r in rows):
        return None
    return max(r.end_date for r in rows)
