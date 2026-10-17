from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


# Dataset Guide + evaluation brief: treat 16 Oct 2026 as "today".
DEFAULT_AS_OF = datetime(2026, 10, 16, tzinfo=timezone.utc)


def _configured_as_of() -> datetime:
    try:
        from app.core.config import get_settings

        raw = (get_settings().evaluation_as_of or "").strip()
        if raw:
            text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return DEFAULT_AS_OF


def parse_as_of(value: str | datetime | None) -> datetime:
    if value is None:
        return _configured_as_of()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def inclusive_date_end_to_exclusive(end_inclusive: date | datetime) -> datetime:
    """Convert an inclusive calendar end date to exclusive next-day UTC midnight."""
    if isinstance(end_inclusive, datetime):
        d = end_inclusive.date()
    else:
        d = end_inclusive
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)


def start_of_day(d: date | datetime) -> datetime:
    if isinstance(d, datetime):
        d = d.date()
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
