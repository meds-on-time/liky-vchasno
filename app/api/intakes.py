
"""Take and snooze endpoints with OpenAPI documentation."""

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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "result": "ok",
                    "taken_at": "2026-11-15T16:05:00Z",
                },
                {
                    "result": "already_taken",
                    "taken_at": "2026-11-15T16:05:00Z",
                },
                {
                    "result": "missed",
                    "taken_at": None,
                },
            ]
        }
    }


class SnoozeResponse(BaseModel):
    result: Literal[
        "ok",
        "already_taken",
        "missed",
        "too_late",
    ]
    remind_at: datetime | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "result": "ok",
                    "remind_at": "2026-11-15T16:15:00Z",
                },
                {
                    "result": "already_taken",
                    "remind_at": None,
                },
                {
                    "result": "missed",
                    "remind_at": None,
                },
                {
                    "result": "too_late",
                    "remind_at": None,
                },
            ]
        }
    }


@router.post(
    "/{intake_id}/take",
    response_model=TakeResponse,
    summary="Підтвердити прийом ліків",
    description=(
        "Позначає запланований прийом препарату як виконаний. "
        "Якщо прийом уже підтверджено, повертає already_taken "
        "із часом першого підтвердження. "
        "Якщо прийом пропущений, повертає missed. "
        "Підтвердження після T+60 не змінює статус пропущеного прийому."
    ),
    responses={
        200: {
            "description": (
                "Результат операції: ok, already_taken або missed."
            )
        },
        404: {
            "description": "Прийом із таким ідентифікатором не знайдено."
        },
        422: {
            "description": "Некоректний ідентифікатор прийому."
        },
    },
)
async def take_intake(
    intake_id: int,
    session: SessionDep,
) -> TakeResponse:
    outcome = await reminders.take(
        session,
        intake_id,
        now_utc(),
    )

    if outcome is None:
        raise HTTPException(
            status_code=404,
            detail="intake not found",
        )

    result, taken_at = outcome

    return TakeResponse(
        result=result,
        taken_at=taken_at,
    )


@router.post(
    "/{intake_id}/snooze",
    response_model=SnoozeResponse,
    summary="Відкласти нагадування на 10 хвилин",
    description=(
        "Відкладає нагадування на 10 хвилин. "
        "Відкладання не змінює початковий час прийому "
        "та контрольні моменти T+30 і T+60. "
        "Після T+50 відкласти нагадування вже не можна "
        "(результат too_late). "
        "Для виконаного прийому повертає already_taken, "
        "для пропущеного — missed."
    ),
    responses={
        200: {
            "description": (
                "Результат операції: ok, already_taken, "
                "missed або too_late."
            )
        },
        404: {
            "description": "Прийом із таким ідентифікатором не знайдено."
        },
        422: {
            "description": "Некоректний ідентифікатор прийому."
        },
    },
)
async def snooze_intake(
    intake_id: int,
    session: SessionDep,
) -> SnoozeResponse:
    outcome = await reminders.snooze(
        session,
        intake_id,
        now_utc(),
    )

    if outcome is None:
        raise HTTPException(
            status_code=404,
            detail="intake not found",
        )

    result, remind_at = outcome

    return SnoozeResponse(
        result=result,
        remind_at=remind_at,
    )
