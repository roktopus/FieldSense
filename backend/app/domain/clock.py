from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


DEFAULT_AS_OF = datetime(2026, 10, 17, tzinfo=timezone.utc)


def parse_as_of(value: str | datetime | None) -> datetime:
    if value is None:
        return DEFAULT_AS_OF
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
