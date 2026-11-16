"""Patients' schedules for the logged-in trusted contact (web cabinet, SCRUM-31)."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.auth import CurrentUser
from app.database import SessionDep
from app.services.patients import patients_of

router = APIRouter(prefix="/contacts", tags=["auth"])


class MedicationOut(BaseModel):
    id: int
    name: str
    dose: str
    form: str | None
    times: list[str]
    end_date: date | None


class PatientOut(BaseModel):
    id: int
    name: str | None
    medications: list[MedicationOut]


class PatientsOut(BaseModel):
    patients: list[PatientOut]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "patients": [
                        {
                            "id": 7,
                            "name": "Олена",
                            "medications": [
                                {
                                    "id": 3,
                                    "name": "Сертралін",
                                    "dose": "50 мг",
                                    "form": "таблетка",
                                    "times": ["08:00", "20:00"],
                                    "end_date": "2026-11-30",
                                }
                            ],
                        }
                    ]
                }
            ]
        }
    }


@router.get(
    "/patients",
    response_model=PatientsOut,
    summary="Розклади моїх підопічних",
    description=(
        "Для довіреної особи, що увійшла в кабінет: люди, які її запросили (/invite), "
        "їхні препарати і час прийомів (Europe/Kyiv, ГГ:ХХ). end_date – останній день курсу "
        "або null. Порожній список – вас ще ніхто не запросив. Чужих пацієнтів не видно."
    ),
    responses={401: {"description": "Немає дійсної сесії"}},
)
async def my_patients(user: CurrentUser, session: SessionDep) -> PatientsOut:
    return PatientsOut(patients=[PatientOut(**p) for p in await patients_of(session, user.id)])
