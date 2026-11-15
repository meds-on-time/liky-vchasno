"""SCRUM-26: alert text for a trusted contact when an intake is missed."""

from datetime import date, datetime, time

from app.models import Intake, Medication
from app.notifications import build_missed_alert_text
from app.services.reminders import Notification
from app.timeutils import KYIV, as_utc

T = datetime.combine(date(2026, 11, 16), time(20, 0), tzinfo=KYIV)


def alert(patient_name):
    intake = Intake(id=7, schedule_id=1, scheduled_at=as_utc(T))
    med = Medication(id=1, user_id=1, name="Сертралін", dose="50 мг")
    return Notification("missed_alert", 200, intake, med, patient_name)


def test_missed_alert_with_patient_name():
    text = build_missed_alert_text(alert("Олена"))
    assert "Олена не відмітив(-ла) прийом" in text
    assert "Сертралін, 50 мг о 20:00" in text  # Kyiv time
    assert "зателефонувати" in text


def test_missed_alert_without_name_uses_neutral_word():
    text = build_missed_alert_text(alert(None))
    assert "Ваш підопічний не відмітив(-ла) прийом" in text
    assert "None" not in text
