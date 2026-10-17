from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class SpillAggregate:
    effective_spill_count: int
    detection_count: int
    known_volume_total: Decimal | None
    missing_volume_count: int
    excluded_ids: list[str]
    spills: list[dict[str, Any]]


def aggregate_spills(
    detections: list[dict[str, Any]],
    *,
    excluded_inspection_ids: set[str] | None = None,
) -> SpillAggregate:
    """Count effective spills after formal detection exclusions. Null volume ≠ 0."""
    excluded = excluded_inspection_ids or set()
    detection_count = len(detections)
    effective: list[dict[str, Any]] = []
    missing = 0
    total = Decimal("0")
    has_any_volume = False

    for row in detections:
        iid = row["inspection_id"]
        if iid in excluded:
            continue
        effective.append(row)
        vol = row.get("volume_bbl")
        if vol is None:
            missing += 1
        else:
            has_any_volume = True
            total += Decimal(str(vol))

    return SpillAggregate(
        effective_spill_count=len(effective),
        detection_count=detection_count,
        known_volume_total=total if has_any_volume else None,
        missing_volume_count=missing,
        excluded_ids=sorted(excluded),
        spills=effective,
    )
