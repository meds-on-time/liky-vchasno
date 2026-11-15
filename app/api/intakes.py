"""Take/snooze endpoints from the API contract.

STUBS for now (SCRUM-13), real logic comes in SCRUM-52.
Response depends on intake_id: 1 -> ok, 2 -> already_taken, 3 -> missed, other -> 404.
"""

from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

KYIV = ZoneInfo("Europe/Kyiv")

router = APIRouter(prefix="/intakes", tags=["intakes"])


class TakeResponse(BaseModel):
    result: Literal["ok", "already_taken", "missed"]
    taken_at: datetime | None = None


class SnoozeResponse(BaseModel):
    result: Literal["ok", "already_taken", "missed"]
    remind_at: datetime | None = None


@router.post("/{intake_id}/take", response_model=TakeResponse)
async def take_intake(intake_id: int) -> TakeResponse:
    now = datetime.now(KYIV)
    if intake_id == 1:
        return TakeResponse(result="ok", taken_at=now)
    if intake_id == 2:
        return TakeResponse(result="already_taken", taken_at=now - timedelta(minutes=5))
    if intake_id == 3:
        return TakeResponse(result="missed")
    raise HTTPException(status_code=404, detail="intake not found")


@router.post("/{intake_id}/snooze", response_model=SnoozeResponse)
async def snooze_intake(intake_id: int) -> SnoozeResponse:
    now = datetime.now(KYIV)
    if intake_id == 1:
        return SnoozeResponse(result="ok", remind_at=now + timedelta(minutes=10))
    if intake_id == 2:
        return SnoozeResponse(result="already_taken")
    if intake_id == 3:
        return SnoozeResponse(result="missed")
    raise HTTPException(status_code=404, detail="intake not found")