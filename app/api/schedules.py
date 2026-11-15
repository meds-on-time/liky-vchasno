"""SCRUM-18: set and read intake times of a medication."""

from datetime import date, datetime, time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import SessionDep
from app.services.schedules import ScheduleError, get_schedule, set_schedule
from app.timeutils import KYIV

router = APIRouter(prefix="/medications", tags=["schedules"])


class ScheduleIn(BaseModel):
    times: list[time]
    start_date: date | None = None


class ScheduleOut(BaseModel):
    medication_id: int
    times: list[time]
    start_date: date | None


@router.put("/{medication_id}/schedule", response_model=ScheduleOut)
async def put_schedule(
    medication_id: int, body: ScheduleIn, session: SessionDep
) -> ScheduleOut:
    start = body.start_date or datetime.now(KYIV).date()
    try:
        rows = await set_schedule(session, medication_id, body.times, start)
    except LookupError:
        raise HTTPException(status_code=404, detail="medication not found")
    except ScheduleError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return ScheduleOut(
        medication_id=medication_id,
        times=[r.time_of_day for r in sorted(rows, key=lambda r: r.time_of_day)],
        start_date=start,
    )


@router.get("/{medication_id}/schedule", response_model=ScheduleOut)
async def read_schedule(
    medication_id: int, session: SessionDep
) -> ScheduleOut:
    rows = await get_schedule(session, medication_id)
    return ScheduleOut(
        medication_id=medication_id,
        times=[r.time_of_day for r in rows],
        start_date=rows[0].start_date if rows else None,
    )