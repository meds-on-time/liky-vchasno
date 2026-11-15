"""SCRUM-14, SCRUM-15: trusted contact invite and consent.

The scheduler already alerts trusted contacts whose contact_id is set
and consent is True (see reminders._alert_chats), so this module only
creates and fills trusted_contacts rows.
"""

import secrets

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EventLog, TrustedContact, User

INVITE_PREFIX = "inv_"

# accept_invite results
OK = "ok"
NOT_FOUND = "not_found"
ALREADY_USED = "already_used"
SELF = "self"
ALREADY_LINKED = "already_linked"


async def create_invite(session: AsyncSession, patient_id: int) -> str:
    """Create a one-time invite code. Consent is off until the patient turns it on."""
    code = secrets.token_urlsafe(8)
    session.add(TrustedContact(patient_id=patient_id, invite_code=code, consent=False))
    session.add(EventLog(user_id=patient_id, event="invite_created"))
    await session.commit()
    return code


async def accept_invite(
    session: AsyncSession, code: str, contact_user_id: int
) -> tuple[str, User | None]:
    """Link the person who opened the link as a trusted contact.

    Returns (result, patient). patient is set for every result except not_found,
    so the bot can tell the patient about the new contact.
    """
    invite = await session.scalar(
        select(TrustedContact).where(TrustedContact.invite_code == code)
    )
    if invite is None:
        return NOT_FOUND, None

    patient = await session.get(User, invite.patient_id)
    if invite.contact_id is not None:
        return ALREADY_USED, patient
    if invite.patient_id == contact_user_id:
        return SELF, patient

    # The same person must not be linked twice: two rows would mean two alerts.
    existing = await session.scalar(
        select(TrustedContact.id).where(
            TrustedContact.patient_id == invite.patient_id,
            TrustedContact.contact_id == contact_user_id,
        )
    )
    if existing is not None:
        return ALREADY_LINKED, patient

    invite.contact_id = contact_user_id
    session.add(EventLog(user_id=contact_user_id, event="invite_accepted"))
    await session.commit()
    return OK, patient


async def linked_contacts(session: AsyncSession, patient_id: int) -> list[User]:
    """Trusted contacts who have opened the invite link."""
    rows = await session.scalars(
        select(User)
        .join(TrustedContact, TrustedContact.contact_id == User.id)
        .where(TrustedContact.patient_id == patient_id)
        .order_by(TrustedContact.id)
    )
    return list(rows)


async def set_consent(session: AsyncSession, patient_id: int, value: bool) -> int:
    """Turn alerts on or off for all linked contacts. Returns how many were changed."""
    result = await session.execute(
        update(TrustedContact)
        .where(
            TrustedContact.patient_id == patient_id,
            TrustedContact.contact_id.is_not(None),
        )
        .values(consent=value)
    )
    count = result.rowcount or 0
    if count:
        event = "consent_on" if value else "consent_off"
        session.add(EventLog(user_id=patient_id, event=event))
    await session.commit()
    return count
