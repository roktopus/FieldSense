"""Coverage-aware refusals when required measurements are absent from the dataset."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db import models


def answer_missing_pressure(db: Session, as_of: datetime) -> dict[str, Any]:
    insp_n = db.query(models.Inspection).count()
    well_n = db.query(models.Well).count()
    return {
        "kind": "short_answer",
        "summary": (
            "I cannot map reservoir pressure across the field. The imported records "
            f"({well_n} wells, {insp_n} inspections as of {as_of.date()}) include wellhead "
            "and ambient temperatures, spill estimates, maintenance and notes — but no "
            "reservoir, bottomhole, tubing or casing pressure measurements. Inventing a "
            "pressure map would be dishonest; load pressure data if you want that view."
        ),
        "visuals": [],
        "rows": None,  # omit empty table — refusal is the answer
        "coverage": {
            "status": "unsupported",
            "missing": ["reservoir_pressure", "tubing_pressure", "casing_pressure"],
            "searched": ["inspections", "maintenance", "context_notes", "fleet_docs"],
        },
        "citations": [
            {"id": "inspections", "label": "Weekly inspections (temps/spills only)"},
            {"id": "fleet", "label": "Well-type manuals (design pressure limits, not field readings)"},
        ],
        "evidence": [],
        "discussed_asset_ids": [],
    }


def answer_missing_production_volume(db: Session, year: int | None, as_of: datetime) -> dict[str, Any]:
    y = year or (as_of.year - 1 if as_of.month == 1 and as_of.day <= 15 else as_of.year)
    return {
        "kind": "short_answer",
        "summary": (
            f"I cannot name the well that produced the most oil in {y}. This dataset has "
            "no oil volume, BOPD or cumulative production fields — only weekly producing / "
            "not-producing classifications from temperature rules. Ranking by producing weeks "
            "would not be barrels of oil. If you need a volume ranking, the production ledger "
            "must be ingested."
        ),
        "visuals": [],
        "rows": None,
        "coverage": {
            "status": "unsupported",
            "missing": ["oil_volume_bbl", "bopd", "cumulative_production"],
            "year": y,
            "searched": ["inspections", "maintenance", "metadata"],
        },
        "citations": [{"id": "inspections", "label": "Temperature-based production status only"}],
        "evidence": [],
        "discussed_asset_ids": [],
    }
