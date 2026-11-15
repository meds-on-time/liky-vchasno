"""Time helpers. All datetimes are stored in UTC; Kyiv time is used for schedules."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")


def as_utc(dt: datetime) -> datetime:
    """Make a datetime timezone-aware UTC (SQLite returns naive values)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def kyiv_datetime(day: date, at: time) -> datetime:
    """Kyiv wall-clock time on a given day, as UTC."""
    return datetime.combine(day, at, tzinfo=KYIV).astimezone(UTC)


def now_utc() -> datetime:
    return datetime.now(UTC)