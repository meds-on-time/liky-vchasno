"""Take/snooze endpoints from the API contract (SCRUM-52)."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import SessionDep
from app.services import reminders
from app.timeutils import now_utc

router = APIRouter(prefix="/intakes", tags=["intakes"])


class TakeResponse(BaseModel):
    result: Literal["ok", "already_taken", "missed"]
    taken_at: datetime | None = None


class SnoozeResponse(BaseModel):
    result: Literal["ok", "already_taken", "missed", "too_late"]
    remind_at: datetime | None = None


@router.post("/{intake_id}/take", response_model=TakeResponse)
async def take_intake(intake_id: int, session: SessionDep) -> TakeResponse:
    outcome = await reminders.take(session, intake_id, now_utc())
    if outcome is None:
        raise HTTPException(status_code=404, detail="intake not found")
    result, taken_at = outcome
    return TakeResponse(result=result, taken_at=taken_at)


@router.post("/{intake_id}/snooze", response_model=SnoozeResponse)
async def snooze_intake(intake_id: int, session: SessionDep) -> SnoozeResponse:
    outcome = await reminders.snooze(session, intake_id, now_utc())
    if outcome is None:
        raise HTTPException(status_code=404, detail="intake not found")
    result, remind_at = outcome
    return SnoozeResponse(result=result, remind_at=remind_at)