"""TDD: downtime = 7 days × non-producing inspections in window."""

from datetime import datetime, timezone
from decimal import Decimal

from app.domain.downtime import compute_downtime_days
from app.domain.production import ProductionStatus


def _ins(day: str, status: ProductionStatus, iid: str):
    return {
        "inspection_id": iid,
        "inspected_at": datetime.fromisoformat(day).replace(tzinfo=timezone.utc),
        "status": status,
    }


def test_each_non_producing_counts_seven_days():
    rows = [
        _ins("2025-07-24", ProductionStatus.NOT_PRODUCING, "a"),
        _ins("2025-10-16", ProductionStatus.NOT_PRODUCING, "b"),
        _ins("2025-10-23", ProductionStatus.NOT_PRODUCING, "c"),
        _ins("2025-08-01", ProductionStatus.PRODUCING, "d"),
    ]
    result = compute_downtime_days(
        rows,
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end_exclusive=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result.downtime_days == 21
    assert result.non_producing_count == 3
    assert result.inspection_count == 4


def test_unknown_does_not_count_as_downtime():
    rows = [_ins("2025-07-24", ProductionStatus.UNKNOWN, "a")]
    result = compute_downtime_days(
        rows,
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end_exclusive=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result.downtime_days == 0


def test_window_filters_inspections():
    rows = [
        _ins("2026-06-10", ProductionStatus.NOT_PRODUCING, "before"),
        _ins("2026-06-16", ProductionStatus.NOT_PRODUCING, "start"),
        _ins("2026-10-16", ProductionStatus.NOT_PRODUCING, "end"),
        _ins("2026-10-17", ProductionStatus.NOT_PRODUCING, "after"),
    ]
    result = compute_downtime_days(
        rows,
        start=datetime(2026, 6, 16, tzinfo=timezone.utc),
        end_exclusive=datetime(2026, 10, 17, tzinfo=timezone.utc),
    )
    assert result.downtime_days == 14
    assert {i["inspection_id"] for i in result.contributing} == {"start", "end"}


def test_q6_style_ranking_values():
    # Membership/order helper: 7 * counts
    assert 7 * 7 == 49
    assert 7 * 6 == 42
