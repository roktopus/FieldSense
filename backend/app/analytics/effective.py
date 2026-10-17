from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.domain.production import ProductionClassification, classify_production


@dataclass
class EffectiveInspection:
    inspection: models.Inspection
    wellhead_temp_c: Decimal | None
    ambient_temp_c: Decimal | None
    spill_detected: bool | None
    spill_volume_bbl: Decimal | None
    excluded_spill: bool
    applied_corrections: list[models.Correction]
    classification: ProductionClassification


def _active_corrections(db: Session, inspection_id: str) -> list[models.Correction]:
    return list(
        db.execute(
            select(models.Correction).where(
                models.Correction.target_id == inspection_id,
                models.Correction.status == "active",
            )
        ).scalars()
    )


def effective_inspection(
    db: Session,
    inspection: models.Inspection,
    well_type: str,
) -> EffectiveInspection:
    corrections = _active_corrections(db, inspection.inspection_id)
    wellhead = inspection.wellhead_temp_c
    ambient = inspection.ambient_temp_c
    spill_detected = inspection.spill_detected
    spill_volume = inspection.spill_est_volume_bbl
    excluded = False

    for corr in corrections:
        if corr.field == "wellhead_temp_c":
            wellhead = Decimal(corr.new_value)
        elif corr.field == "ambient_temp_c":
            ambient = Decimal(corr.new_value)
        elif corr.field == "spill_est_volume_bbl":
            spill_volume = Decimal(corr.new_value)
            if spill_volume > 0:
                spill_detected = True
        elif corr.field in {"spill_detected", "detection"}:
            val = corr.new_value.lower()
            if val in {"false", "0", "excluded", "rainwater", "not_spill"}:
                spill_detected = False
                excluded = True
                spill_volume = None
            elif val in {"true", "1"}:
                spill_detected = True

    # Formal source notes of type "correction" exclude false-positive spill detections
    notes = db.execute(
        select(models.SourceNote).where(
            models.SourceNote.inspection_id == inspection.inspection_id,
            models.SourceNote.note_type == "correction",
        )
    ).scalars().all()
    for note in notes:
        text = (note.text or "").lower()
        excludes = (
            "not a spill" in text
            or "not a crude spill" in text
            or "rainwater" in text
            or "not crude" in text
            or "no crude" in text
            or "shadow from the pump jack" in text
            or "wet soil after rain" in text
            or "produced water" in text
        )
        if excludes:
            spill_detected = False
            excluded = True
            spill_volume = None
            break

    classification = classify_production(wellhead, ambient, well_type)
    return EffectiveInspection(
        inspection=inspection,
        wellhead_temp_c=wellhead,
        ambient_temp_c=ambient,
        spill_detected=spill_detected,
        spill_volume_bbl=spill_volume,
        excluded_spill=excluded,
        applied_corrections=corrections,
        classification=classification,
    )
