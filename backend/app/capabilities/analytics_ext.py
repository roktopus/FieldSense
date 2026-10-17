"""Final-set analytics: hotter region, wait reasons, repair-risk ranking."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.domain.production import ProductionStatus, classify_production


ANOMALY_PAT = re.compile(
    r"squeal|rattl|knock|vibrat|behav|sound|noise|grind|hot\s+bearing|smell(?!ed\s+gas)|"
    r"pump\s+jack.*(wrong|odd|strange)|running\s+rough|behaving",
    re.I,
)
WAIT_PARTS = re.compile(r"waiting on (?:replacement )?parts|parts from the vendor|back[\s-]?order", re.I)
WAIT_CREW = re.compile(r"waiting on (?:a )?crew|crew unavailable|rig delayed|workover rig", re.I)
WAIT_CONTRACTOR = re.compile(r"waiting on (?:the )?contractor|contractor delay", re.I)
WAIT_WEATHER = re.compile(r"waiting on weather|delayed by weather|weather delay", re.I)


def hotter_regions(db: Session, *, as_of: datetime, lookback_days: int = 90) -> dict[str, Any]:
    start = as_of - timedelta(days=lookback_days)
    rows_raw = (
        db.query(models.Inspection, models.Well, models.Area)
        .join(models.Well, models.Well.asset_id == models.Inspection.asset_id)
        .join(models.Area, models.Area.area_id == models.Well.area_id)
        .filter(
            models.Inspection.inspected_at >= start,
            models.Inspection.inspected_at <= as_of,
            models.Inspection.wellhead_temp_c.isnot(None),
            models.Inspection.ambient_temp_c.isnot(None),
        )
        .all()
    )
    by_area: dict[str, list[float]] = defaultdict(list)
    for insp, well, area in rows_raw:
        delta = float(insp.wellhead_temp_c - insp.ambient_temp_c)
        by_area[area.name].append(delta)
    rows = []
    for area_name, vals in by_area.items():
        rows.append(
            {
                "area_name": area_name,
                "mean_delta_c": round(sum(vals) / len(vals), 2),
                "median_delta_c": round(float(median(vals)), 2),
                "samples": len(vals),
            }
        )
    rows.sort(key=lambda r: r["mean_delta_c"], reverse=True)
    top = rows[0] if rows else None
    return {
        "rows": rows,
        "hottest": top,
        "window_days": lookback_days,
        "as_of": as_of.isoformat(),
    }


def wait_reasons_by_area(db: Session, *, year: int, as_of: datetime) -> dict[str, Any]:
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = min(as_of, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
    notes = (
        db.query(models.SourceNote, models.Well, models.Area)
        .join(models.Well, models.Well.asset_id == models.SourceNote.asset_id)
        .join(models.Area, models.Area.area_id == models.Well.area_id)
        .filter(
            models.SourceNote.note_type == "operator_note",
            models.SourceNote.created_at >= start,
            models.SourceNote.created_at <= end,
        )
        .all()
    )
    # reason -> area -> list of extra-day estimates from note text
    bucket: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    day_pat = re.compile(r"(\d+)\s*day", re.I)
    for note, well, area in notes:
        text = note.text or ""
        reason = None
        if WAIT_PARTS.search(text):
            reason = "parts"
        elif WAIT_CREW.search(text):
            reason = "crews"
        elif WAIT_CONTRACTOR.search(text):
            reason = "contractors"
        elif WAIT_WEATHER.search(text):
            reason = "weather"
        if not reason:
            continue
        days_m = day_pat.search(text)
        extra = float(days_m.group(1)) if days_m else 7.0
        bucket[reason][area.name].append(extra)

    areas = sorted({a.name for a in db.query(models.Area).all()})
    table_rows: list[dict[str, Any]] = []
    stacked: list[dict[str, Any]] = []
    for area in areas:
        total = sum(len(bucket[r].get(area, [])) for r in ("parts", "crews", "contractors", "weather"))
        if total == 0:
            continue
        entry = {"area_name": area, "parts": 0, "crews": 0, "contractors": 0, "weather": 0}
        for reason in ("parts", "crews", "contractors", "weather"):
            vals = bucket[reason].get(area, [])
            share = round(100.0 * len(vals) / total, 1) if total else 0
            typ = round(sum(vals) / len(vals), 1) if vals else 0
            table_rows.append(
                {
                    "area_name": area,
                    "reason": reason,
                    "count": len(vals),
                    "share_pct": share,
                    "typical_extra_days": typ,
                }
            )
            entry[reason] = len(vals)
        stacked.append(entry)

    # Highlight standout area by total wait notes
    standout = None
    if stacked:
        standout = max(stacked, key=lambda r: r["parts"] + r["crews"] + r["contractors"] + r["weather"])
    return {
        "rows": table_rows,
        "stacked": stacked,
        "standout_area": standout["area_name"] if standout else None,
        "year": year,
    }


def repair_risk_rank(
    db: Session,
    *,
    as_of: datetime,
    lookback_days: int = 30,
    top_n: int = 10,
) -> dict[str, Any]:
    start = as_of - timedelta(days=lookback_days)
    notes = (
        db.query(models.SourceNote)
        .filter(
            models.SourceNote.note_type == "operator_note",
            models.SourceNote.created_at >= start,
            models.SourceNote.created_at <= as_of,
        )
        .order_by(models.SourceNote.created_at.desc())
        .all()
    )
    candidates: dict[str, dict[str, Any]] = {}
    for note in notes:
        if not ANOMALY_PAT.search(note.text or ""):
            continue
        # Skip if a non-spill corrective repair started after the note
        later = (
            db.query(models.Maintenance)
            .filter(
                models.Maintenance.asset_id == note.asset_id,
                models.Maintenance.started_at > note.created_at,
                models.Maintenance.started_at <= as_of,
                models.Maintenance.maintenance_type == "corrective",
            )
            .all()
        )
        spillish = [m for m in later if m.equipment_kind == "flowline" or (m.issue and "spill" in m.issue.lower())]
        non_spill = [m for m in later if m not in spillish]
        if non_spill:
            continue
        well = db.get(models.Well, note.asset_id)
        area = db.get(models.Area, well.area_id) if well else None
        last_rep = (
            db.query(models.Maintenance)
            .filter(models.Maintenance.asset_id == note.asset_id)
            .order_by(models.Maintenance.started_at.desc())
            .first()
        )
        # Warning signs: recent not-producing or falling delta
        warning = []
        latest_insp = (
            db.query(models.Inspection)
            .filter(
                models.Inspection.asset_id == note.asset_id,
                models.Inspection.inspected_at <= as_of,
            )
            .order_by(models.Inspection.inspected_at.desc())
            .first()
        )
        if latest_insp and well:
            cls = classify_production(
                latest_insp.wellhead_temp_c, latest_insp.ambient_temp_c, well.well_type
            )
            if cls.status == ProductionStatus.NOT_PRODUCING:
                warning.append("Latest inspection: not producing")
            if cls.delta_c is not None:
                warning.append(f"Latest ΔT={cls.delta_c}°C")
        score = 1.0
        if warning:
            score += 0.5
        if note.asset_id not in candidates or note.created_at > candidates[note.asset_id]["note_at"]:
            candidates[note.asset_id] = {
                "asset_id": note.asset_id,
                "area_name": area.name if area else None,
                "note_quote": (note.text or "")[:220],
                "note_at": note.created_at,
                "note_date": note.created_at.date().isoformat(),
                "other_warning_signs": "; ".join(warning) if warning else "none",
                "last_repair": (
                    f"{last_rep.maintenance_id} ({last_rep.started_at.date().isoformat()})"
                    if last_rep
                    else "none on record"
                ),
                "score": score,
            }
    ranked = sorted(candidates.values(), key=lambda r: (-r["score"], -r["note_at"].timestamp()))
    rows = []
    for i, r in enumerate(ranked[:top_n], start=1):
        rows.append(
            {
                "rank": i,
                "asset_id": r["asset_id"],
                "area_name": r["area_name"],
                "operator_note_evidence": f"{r['note_date']}: {r['note_quote']}",
                "other_warning_signs": r["other_warning_signs"],
                "last_repair": r["last_repair"],
            }
        )
    return {"rows": rows, "count": len(rows)}
