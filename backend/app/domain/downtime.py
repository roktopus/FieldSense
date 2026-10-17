from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.production import ProductionStatus


@dataclass
class DowntimeResult:
    downtime_days: int
    non_producing_count: int
    inspection_count: int
    contributing: list[dict[str, Any]] = field(default_factory=list)


def compute_downtime_days(
    inspections: list[dict[str, Any]],
    *,
    start: datetime,
    end_exclusive: datetime,
) -> DowntimeResult:
    """Each non-producing inspection in [start, end_exclusive) contributes 7 days."""
    in_window = [
        row
        for row in inspections
        if start <= row["inspected_at"] < end_exclusive
    ]
    contributing = [
        row for row in in_window if row["status"] == ProductionStatus.NOT_PRODUCING
    ]
    return DowntimeResult(
        downtime_days=7 * len(contributing),
        non_producing_count=len(contributing),
        inspection_count=len(in_window),
        contributing=contributing,
    )
