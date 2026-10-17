"""Regulator letter compliance (soil samples after reportable NE spills)."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.effective import effective_inspection
from app.db import models


def _letter_scope(db: Session) -> dict[str, Any]:
    doc = (
        db.query(models.Document)
        .filter(models.Document.doc_key.like("%regulator-letter%"))
        .first()
    )
    areas = ["Northeast Block 7", "Northeast Block 8"]
    since = date(2026, 6, 1)
    threshold = Decimal("5")
    due = date(2027, 1, 15)
    compliance_phrase = "Soil samples sent to the lab."
    if doc:
        if "Northeast Block 7" in doc.body:
            areas = []
            for name in ["Northeast Block 7", "Northeast Block 8"]:
                if name in doc.body:
                    areas.append(name)
        m = re.search(r"since\s+(\d{1,2}\s+\w+\s+20\d{2})", doc.body, re.I)
        if m:
            for fmt in ("%d %b %Y", "%d %B %Y"):
                try:
                    since = datetime.strptime(m.group(1), fmt).date()
                    break
                except ValueError:
                    pass
        if "Soil samples sent to the lab" in doc.body:
            compliance_phrase = "Soil samples sent to the lab."
    return {
        "areas": areas,
        "since": since,
        "threshold_bbl": threshold,
        "due": due,
        "compliance_phrase": compliance_phrase,
        "doc_key": doc.doc_key if doc else None,
    }


def letter_spill_compliance(db: Session, *, as_of: datetime) -> dict[str, Any]:
    scope = _letter_scope(db)
    area_ids = [
        a.area_id
        for a in db.query(models.Area).filter(models.Area.name.in_(scope["areas"])).all()
    ]
    wells = db.query(models.Well).filter(models.Well.area_id.in_(area_ids)).all() if area_ids else []
    start_dt = datetime(scope["since"].year, scope["since"].month, scope["since"].day, tzinfo=timezone.utc)
    rows: list[dict[str, Any]] = []
    for well in wells:
        area = db.get(models.Area, well.area_id)
        inspections = (
            db.query(models.Inspection)
            .filter(
                models.Inspection.asset_id == well.asset_id,
                models.Inspection.inspected_at >= start_dt,
                models.Inspection.inspected_at <= as_of,
                models.Inspection.spill_detected.is_(True),
            )
            .all()
        )
        for insp in inspections:
            eff = effective_inspection(db, insp, well.well_type)
            if eff.excluded_spill or not eff.spill_detected:
                continue
            vol = eff.spill_volume_bbl
            if vol is None or vol < scope["threshold_bbl"]:
                continue
            # Find clean-up job linked to this inspection
            mnt = (
                db.query(models.Maintenance)
                .filter(models.Maintenance.triggered_by_inspection_id == insp.inspection_id)
                .first()
            )
            soil_ok = False
            cleanup_id = None
            if mnt:
                cleanup_id = mnt.maintenance_id
                fact = (
                    db.query(models.ExtractedFact)
                    .filter(
                        models.ExtractedFact.maintenance_id == mnt.maintenance_id,
                        models.ExtractedFact.fact_type == "soil_samples_lab",
                    )
                    .first()
                )
                if fact:
                    soil_ok = True
                else:
                    # Fallback: scan report document body
                    doc = (
                        db.query(models.Document)
                        .filter(models.Document.doc_key == f"{well.asset_id}/{mnt.report_file}")
                        .first()
                    )
                    if doc and scope["compliance_phrase"].rstrip(".") in doc.body:
                        soil_ok = True
            compliant = "Yes" if soil_ok else "No"
            reason = (
                "Clean-up report records soil samples sent to the lab."
                if soil_ok
                else "No clean-up report sentence “Soil samples sent to the lab.” (field readings do not count)."
            )
            rows.append(
                {
                    "asset_id": well.asset_id,
                    "area_name": area.name if area else None,
                    "inspection": f"{insp.inspection_id} ({insp.inspected_at.date().isoformat()})",
                    "volume_bbl": float(vol),
                    "cleanup_job": cleanup_id or "none",
                    "compliant": f"{compliant} — {reason}",
                }
            )
    rows.sort(key=lambda r: (r["area_name"] or "", r["asset_id"], r["inspection"]))
    return {"count": len(rows), "rows": rows, "scope": scope}
