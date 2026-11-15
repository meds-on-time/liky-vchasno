
"""Schedule endpoints with OpenAPI documentation."""

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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "times": ["08:00", "20:00"],
                    "start_date": "2026-11-15",
                }
            ]
        }
    }


class ScheduleOut(BaseModel):
    medication_id: int
    times: list[time]
    start_date: date | None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "medication_id": 1,
                    "times": ["08:00", "20:00"],
                    "start_date": "2026-11-15",
                }
            ]
        }
    }


@router.put(
    "/{medication_id}/schedule",
    response_model=ScheduleOut,
    summary="Створити або оновити розклад прийому ліків",
    description=(
        "Зберігає час прийому зазначеного препарату. "
        "Час задається у форматі ГГ:ХХ за часовим поясом "
        "Europe/Kyiv. Можна вказати декілька прийомів на день. "
        "Якщо start_date не передано, використовується "
        "поточна дата за Києвом. "
        "Між прийомами одного препарату має бути "
        "щонайменше 60 хвилин."
    ),
    responses={
        200: {
            "description": "Розклад успішно збережено."
        },
        404: {
            "description": "Препарат не знайдено."
        },
        422: {
            "description": (
                "Некоректні дані розкладу або порушення "
                "правил часу прийому."
            )
        },
    },
)
async def put_schedule(
    medication_id: int,
    body: ScheduleIn,
    session: SessionDep,
) -> ScheduleOut:
    start = body.start_date or datetime.now(KYIV).date()

    try:
        rows = await set_schedule(
            session,
            medication_id,
            body.times,
            start,
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail="medication not found",
        )
    except ScheduleError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return ScheduleOut(
        medication_id=medication_id,
        times=[
            r.time_of_day
            for r in sorted(rows, key=lambda r: r.time_of_day)
        ],
        start_date=start,
    )


@router.get(
    "/{medication_id}/schedule",
    response_model=ScheduleOut,
    summary="Отримати розклад прийому препарату",
    description=(
        "Повертає збережений розклад прийому препарату "
        "за його ідентифікатором. "
        "Результат містить список часів прийому "
        "та дату початку розкладу. "
        "Якщо розклад відсутній, список times буде порожнім, "
        "а start_date матиме значення null."
    ),
    responses={
        200: {
            "description": "Інформацію про розклад отримано."
        },
        422: {
            "description": "Некоректний ідентифікатор препарату."
        },
    },
)
async def read_schedule(
    medication_id: int,
    session: SessionDep,
) -> ScheduleOut:
    rows = await get_schedule(session, medication_id)

    return ScheduleOut(
        medication_id=medication_id,
        times=[r.time_of_day for r in rows],
        start_date=rows[0].start_date if rows else None,
    )
