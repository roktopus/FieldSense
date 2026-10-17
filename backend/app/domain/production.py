from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ProductionStatus(str, Enum):
    PRODUCING = "producing"
    NOT_PRODUCING = "not_producing"
    UNKNOWN = "unknown"


# Extracted from fleet/well-types manuals (T200 §9.3, T350, T500 §3).
THRESHOLDS_C: dict[str, Decimal] = {
    "T200": Decimal("15"),
    "T350": Decimal("20"),
    "T500": Decimal("25"),
}


@dataclass(frozen=True)
class ProductionClassification:
    status: ProductionStatus
    delta_c: Decimal | None
    threshold_c: Decimal | None
    well_type: str | None
    limitations: tuple[str, ...] = ()


def classify_production(
    wellhead_c: Decimal | float | None,
    ambient_c: Decimal | float | None,
    well_type: str | None,
) -> ProductionClassification:
    if well_type not in THRESHOLDS_C:
        return ProductionClassification(
            status=ProductionStatus.UNKNOWN,
            delta_c=None,
            threshold_c=None,
            well_type=well_type,
            limitations=("unknown_or_unsupported_well_type",),
        )
    if wellhead_c is None or ambient_c is None:
        return ProductionClassification(
            status=ProductionStatus.UNKNOWN,
            delta_c=None,
            threshold_c=THRESHOLDS_C[well_type],
            well_type=well_type,
            limitations=("missing_temperature_reading",),
        )
    wh = Decimal(str(wellhead_c))
    amb = Decimal(str(ambient_c))
    delta = wh - amb
    threshold = THRESHOLDS_C[well_type]
    status = (
        ProductionStatus.PRODUCING
        if delta >= threshold
        else ProductionStatus.NOT_PRODUCING
    )
    return ProductionClassification(
        status=status,
        delta_c=delta,
        threshold_c=threshold,
        well_type=well_type,
    )
