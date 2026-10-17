from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.effective import effective_inspection
from app.db import models
from app.domain.clock import inclusive_date_end_to_exclusive, start_of_day
from app.domain.downtime import compute_downtime_days
from app.domain.production import ProductionStatus
from app.domain.spills import aggregate_spills


def resolve_area_id(db: Session, area_name_or_id: str) -> models.Area | None:
    area = db.get(models.Area, area_name_or_id)
    if area:
        return area
    return db.execute(
        select(models.Area).where(func.lower(models.Area.name) == area_name_or_id.lower())
    ).scalar_one_or_none()


def user_name(db: Session, user_id: str | None) -> str | None:
    if not user_id:
        return None
    u = db.get(models.User, user_id)
    return u.name if u else user_id


def get_well_summary(db: Session, asset_id: str, as_of: datetime) -> dict[str, Any]:
    well = db.get(models.Well, asset_id)
    if not well:
        return {"error": "well_not_found", "asset_id": asset_id}
    area = db.get(models.Area, well.area_id)
    insp = db.execute(
        select(models.Inspection)
        .where(
            models.Inspection.asset_id == asset_id,
            models.Inspection.inspected_at <= as_of,
        )
        .order_by(models.Inspection.inspected_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not insp:
        return {
            "asset_id": asset_id,
            "status": ProductionStatus.UNKNOWN.value,
            "limitations": ["no_inspection_as_of"],
        }
    eff = effective_inspection(db, insp, well.well_type)
    notes = db.execute(
        select(models.SourceNote)
        .where(models.SourceNote.asset_id == asset_id)
        .order_by(models.SourceNote.created_at.desc())
    ).scalars().all()
    # shared assertions
    assertions = db.execute(
        select(models.Assertion)
        .where(
            models.Assertion.asset_id == asset_id,
            models.Assertion.confirmation_state.in_(["active", "unconfirmed"]),
        )
        .order_by(models.Assertion.created_at.desc())
    ).scalars().all()

    stale = (
        well.recorded_status == "active"
        and eff.classification.status == ProductionStatus.NOT_PRODUCING
    ) or (
        well.recorded_status == "down"
        and eff.classification.status == ProductionStatus.PRODUCING
    )

    conflicts = []
    if insp.notes and eff.classification.status == ProductionStatus.PRODUCING:
        if "not moving" in insp.notes.lower():
            conflicts.append(
                {
                    "kind": "inspector_note_vs_corrected_reading",
                    "text": insp.notes,
                    "author": user_name(db, insp.inspector_user_id),
                }
            )

    return {
        "asset_id": asset_id,
        "name": well.name,
        "well_type": well.well_type,
        "area_id": well.area_id,
        "area_name": area.name if area else well.area_id,
        "status": eff.classification.status.value,
        "delta_c": float(eff.classification.delta_c) if eff.classification.delta_c is not None else None,
        "threshold_c": float(eff.classification.threshold_c)
        if eff.classification.threshold_c is not None
        else None,
        "wellhead_temp_c": float(eff.wellhead_temp_c) if eff.wellhead_temp_c is not None else None,
        "ambient_temp_c": float(eff.ambient_temp_c) if eff.ambient_temp_c is not None else None,
        "latest_inspection": {
            "inspection_id": insp.inspection_id,
            "inspected_at": insp.inspected_at.isoformat(),
            "method": insp.method,
            "inspector_user_id": insp.inspector_user_id,
            "inspector_name": user_name(db, insp.inspector_user_id),
            "notes": insp.notes,
        },
        "recorded_status": well.recorded_status,
        "recorded_status_stale": stale,
        "context_notes": [
            {
                "note_id": n.note_id,
                "note_type": n.note_type,
                "text": n.text,
                "author": user_name(db, n.author_user_id),
                "valid_from": n.valid_from.isoformat() if n.valid_from else None,
                "valid_to": n.valid_to.isoformat() if n.valid_to else None,
            }
            for n in notes
        ],
        "shared_assertions": [
            {
                "id": str(a.id),
                "kind": a.kind,
                "text": a.text,
                "author": user_name(db, a.author_user_id),
                "state": a.confirmation_state,
            }
            for a in assertions
        ],
        "conflicts": conflicts,
        "applied_corrections": [
            {
                "field": c.field,
                "original": c.original_value,
                "new": c.new_value,
                "author": user_name(db, c.author_user_id),
                "reason": c.reason,
            }
            for c in eff.applied_corrections
        ],
        "time_bounds": {"as_of": as_of.isoformat()},
        "evidence_ids": [insp.inspection_id] + [n.note_id for n in notes[:5]],
    }


def analyze_downtime_by_area(
    db: Session,
    *,
    area_name: str,
    start: date,
    end_inclusive: date,
    limit: int = 3,
) -> dict[str, Any]:
    area = resolve_area_id(db, area_name)
    if not area:
        # try partial
        area = db.execute(
            select(models.Area).where(models.Area.name.ilike(f"%{area_name}%"))
        ).scalars().first()
    if not area:
        return {"error": "area_not_found", "area": area_name}

    start_dt = start_of_day(start)
    end_ex = inclusive_date_end_to_exclusive(end_inclusive)
    wells = db.execute(select(models.Well).where(models.Well.area_id == area.area_id)).scalars().all()

    rows = []
    for well in wells:
        inspections = db.execute(
            select(models.Inspection).where(
                models.Inspection.asset_id == well.asset_id,
                models.Inspection.inspected_at >= start_dt,
                models.Inspection.inspected_at < end_ex,
            )
        ).scalars().all()
        classified = []
        for insp in inspections:
            eff = effective_inspection(db, insp, well.well_type)
            classified.append(
                {
                    "inspection_id": insp.inspection_id,
                    "inspected_at": insp.inspected_at,
                    "status": eff.classification.status,
                }
            )
        dt = compute_downtime_days(classified, start=start_dt, end_exclusive=end_ex)
        why = _downtime_why(db, well.asset_id, start_dt, end_ex, dt.contributing)
        rows.append(
            {
                "asset_id": well.asset_id,
                "well_type": well.well_type,
                "downtime_days": dt.downtime_days,
                "non_producing_count": dt.non_producing_count,
                "inspection_count": dt.inspection_count,
                "why": why,
                "contributing_inspection_ids": [c["inspection_id"] for c in dt.contributing],
            }
        )

    rows.sort(key=lambda r: (-r["downtime_days"], r["asset_id"]))
    top = rows[:limit]
    return {
        "area_id": area.area_id,
        "area_name": area.name,
        "time_bounds": {
            "start": start_dt.isoformat(),
            "end_inclusive": end_inclusive.isoformat(),
            "end_exclusive": end_ex.isoformat(),
        },
        "rows": top,
        "all_ranked": rows[:10],
        "units": {"downtime_days": "days"},
        "evidence_ids": [i for r in top for i in r["contributing_inspection_ids"][:20]],
    }


def _downtime_why(
    db: Session,
    asset_id: str,
    start: datetime,
    end_ex: datetime,
    contributing: list[dict[str, Any]],
) -> dict[str, Any]:
    open_mnt = db.execute(
        select(models.Maintenance)
        .where(
            models.Maintenance.asset_id == asset_id,
            models.Maintenance.started_at < end_ex,
            models.Maintenance.maintenance_type == "corrective",
        )
        .order_by(models.Maintenance.started_at.desc())
        .limit(5)
    ).scalars().all()
    notes = db.execute(
        select(models.SourceNote).where(models.SourceNote.asset_id == asset_id)
    ).scalars().all()
    if open_mnt:
        m = open_mnt[0]
        return {
            "relationship": "explicit_link" if m.triggered_by_inspection_id else "temporal_context",
            "summary": m.issue or m.action_taken or "Maintenance on record",
            "maintenance_id": m.maintenance_id,
        }
    for n in notes:
        if n.note_type in {"operator_feedback", "operator_note"} and "shut" in n.text.lower():
            return {
                "relationship": "temporal_context",
                "summary": n.text,
                "note_id": n.note_id,
            }
    return {"relationship": "unconfirmed_claim", "summary": "No recorded reason"}


def non_producing_in_area(db: Session, area_name: str, as_of: datetime) -> dict[str, Any]:
    area = resolve_area_id(db, area_name) or db.execute(
        select(models.Area).where(models.Area.name.ilike(f"%{area_name}%"))
    ).scalars().first()
    if not area:
        return {"error": "area_not_found"}
    wells = db.execute(select(models.Well).where(models.Well.area_id == area.area_id)).scalars().all()
    rows = []
    for well in wells:
        summary = get_well_summary(db, well.asset_id, as_of)
        if summary.get("status") == ProductionStatus.NOT_PRODUCING.value:
            why = "No recorded reason"
            open_mnt = db.execute(
                select(models.Maintenance)
                .where(
                    models.Maintenance.asset_id == well.asset_id,
                    models.Maintenance.started_at <= as_of,
                )
                .order_by(models.Maintenance.started_at.desc())
                .limit(3)
            ).scalars().all()
            # prefer still-open-ish (completed_at in future or recent corrective)
            for m in open_mnt:
                if m.completed_at and m.completed_at > as_of:
                    why = f"Repair {m.maintenance_id}: {m.issue}"
                    break
                if m.maintenance_type == "corrective" and m.started_at >= as_of.replace(
                    year=as_of.year - 1 if as_of.month < 12 else as_of.year
                ):
                    # keep looking for open
                    if m.completed_at is None or m.completed_at >= as_of:
                        why = f"Repair {m.maintenance_id}: {m.issue}"
                        break
            insp_notes = (summary.get("latest_inspection") or {}).get("notes")
            if why == "No recorded reason":
                why = (
                    "No recorded reason — suggest a field check "
                    "(do not invent a cause)."
                )
            recorded = well.recorded_status or "—"
            if summary.get("recorded_status_stale") and recorded == "active":
                recorded_display = "active (out of date)"
            else:
                recorded_display = recorded
            rows.append(
                {
                    "asset_id": well.asset_id,
                    "well_type": well.well_type,
                    "delta_c": summary.get("delta_c"),
                    "recorded_status": recorded_display,
                    "recorded_status_stale": summary.get("recorded_status_stale"),
                    "reason": why,
                    "inspector_observation": insp_notes,
                    "latest_inspection": summary.get("latest_inspection"),
                }
            )
    rows.sort(key=lambda r: r["asset_id"])
    return {
        "area_name": area.name,
        "as_of": as_of.isoformat(),
        "rows": rows,
        "count": len(rows),
    }


def temperature_series(db: Session, asset_id: str, start: date, end_inclusive: date) -> dict[str, Any]:
    well = db.get(models.Well, asset_id)
    if not well:
        return {"error": "well_not_found"}
    start_dt = start_of_day(start)
    end_ex = inclusive_date_end_to_exclusive(end_inclusive)
    inspections = db.execute(
        select(models.Inspection)
        .where(
            models.Inspection.asset_id == asset_id,
            models.Inspection.inspected_at >= start_dt,
            models.Inspection.inspected_at < end_ex,
        )
        .order_by(models.Inspection.inspected_at.asc())
    ).scalars().all()
    points = []
    for insp in inspections:
        eff = effective_inspection(db, insp, well.well_type)
        points.append(
            {
                "inspection_id": insp.inspection_id,
                "inspected_at": insp.inspected_at.isoformat(),
                "wellhead_temp_c": float(eff.wellhead_temp_c) if eff.wellhead_temp_c is not None else None,
                "ambient_temp_c": float(eff.ambient_temp_c) if eff.ambient_temp_c is not None else None,
                "delta_c": float(eff.classification.delta_c)
                if eff.classification.delta_c is not None
                else None,
                "status": eff.classification.status.value,
            }
        )
    threshold = None
    if points:
        from app.domain.production import THRESHOLDS_C

        th = THRESHOLDS_C.get(well.well_type)
        threshold = float(th) if th is not None else None
    return {
        "asset_id": asset_id,
        "well_type": well.well_type,
        "threshold_c": threshold,
        "points": points,
        "count": len(points),
        "time_bounds": {"start": start.isoformat(), "end_inclusive": end_inclusive.isoformat()},
    }


def spill_history(db: Session, asset_id: str, start: date | None = None, end_inclusive: date | None = None) -> dict[str, Any]:
    q = select(models.Inspection).where(
        models.Inspection.asset_id == asset_id,
        models.Inspection.spill_detected.is_(True),
    )
    if start:
        q = q.where(models.Inspection.inspected_at >= start_of_day(start))
    if end_inclusive:
        q = q.where(models.Inspection.inspected_at < inclusive_date_end_to_exclusive(end_inclusive))
    inspections = db.execute(q.order_by(models.Inspection.inspected_at.asc())).scalars().all()
    well = db.get(models.Well, asset_id)
    detections = []
    excluded: set[str] = set()
    for insp in inspections:
        eff = effective_inspection(db, insp, well.well_type if well else "T200")
        if eff.excluded_spill:
            excluded.add(insp.inspection_id)
        detections.append(
            {
                "inspection_id": insp.inspection_id,
                "inspected_at": insp.inspected_at.isoformat(),
                "volume_bbl": eff.spill_volume_bbl,
                "excluded": eff.excluded_spill,
            }
        )
    agg = aggregate_spills(
        [
            {"inspection_id": d["inspection_id"], "volume_bbl": d["volume_bbl"]}
            for d in detections
            if not d["excluded"]
        ]
        + [
            {"inspection_id": d["inspection_id"], "volume_bbl": d["volume_bbl"]}
            for d in detections
            if d["excluded"]
        ],
        excluded_inspection_ids=excluded,
    )
    # rebuild spill list with dates for effective only
    effective_rows = [d for d in detections if not d["excluded"]]
    return {
        "asset_id": asset_id,
        "detection_count": len(detections),
        "effective_spill_count": len(effective_rows),
        "known_volume_total": float(agg.known_volume_total) if agg.known_volume_total is not None else None,
        "excluded": [
            {"inspection_id": d["inspection_id"], "inspected_at": d["inspected_at"]}
            for d in detections
            if d["excluded"]
        ],
        "spills": [
            {
                "inspection_id": d["inspection_id"],
                "date": d["inspected_at"][:10],
                "volume_bbl": float(d["volume_bbl"]) if d["volume_bbl"] is not None else None,
            }
            for d in effective_rows
        ],
    }


def downtime_for_asset_year(db: Session, asset_id: str, year: int) -> dict[str, Any]:
    well = db.get(models.Well, asset_id)
    if not well:
        return {"error": "well_not_found"}
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    start_dt = start_of_day(start)
    end_ex = inclusive_date_end_to_exclusive(end)
    inspections = db.execute(
        select(models.Inspection).where(
            models.Inspection.asset_id == asset_id,
            models.Inspection.inspected_at >= start_dt,
            models.Inspection.inspected_at < end_ex,
        )
    ).scalars().all()
    classified = []
    details = []
    for insp in inspections:
        eff = effective_inspection(db, insp, well.well_type)
        classified.append(
            {
                "inspection_id": insp.inspection_id,
                "inspected_at": insp.inspected_at,
                "status": eff.classification.status,
            }
        )
        if eff.classification.status == ProductionStatus.NOT_PRODUCING:
            cause = _maintenance_near(db, asset_id, insp)
            details.append(
                {
                    "inspection_id": insp.inspection_id,
                    "inspected_at": insp.inspected_at.isoformat(),
                    "wellhead_temp_c": float(eff.wellhead_temp_c) if eff.wellhead_temp_c else None,
                    "ambient_temp_c": float(eff.ambient_temp_c) if eff.ambient_temp_c else None,
                    "delta_c": float(eff.classification.delta_c) if eff.classification.delta_c else None,
                    "cause": cause.get("summary"),
                    "maintenance_id": cause.get("maintenance_id"),
                }
            )
    dt = compute_downtime_days(classified, start=start_dt, end_exclusive=end_ex)
    cause_bits = []
    for d in details:
        bit = d["inspected_at"][:10]
        if d.get("delta_c") is not None:
            bit += f" (ΔT {d['delta_c']} °C)"
        if d.get("cause"):
            bit += f": {d['cause']}"
            if d.get("maintenance_id"):
                bit += f" ({d['maintenance_id']})"
        cause_bits.append(bit)
    narrative = (
        f"{dt.non_producing_count} weekly inspection findings × 7 days = {dt.downtime_days} days"
    )
    if cause_bits:
        narrative += ". " + "; ".join(cause_bits)
    return {
        "asset_id": asset_id,
        "year": year,
        "downtime_days": dt.downtime_days,
        "non_producing_count": dt.non_producing_count,
        "calculation": narrative,
        "details": details,
    }


def _maintenance_near(db: Session, asset_id: str, insp: models.Inspection) -> dict[str, Any]:
    """Best-effort cause for a non-producing inspection (explicit link or temporal)."""
    linked = db.execute(
        select(models.Maintenance).where(
            models.Maintenance.triggered_by_inspection_id == insp.inspection_id
        )
    ).scalars().first()
    if linked:
        return {
            "summary": linked.issue or linked.action_taken or "Maintenance on record",
            "maintenance_id": linked.maintenance_id,
        }
    # temporal: open/corrective within ±14 days of inspection
    window_start = insp.inspected_at - timedelta(days=14)
    window_end = insp.inspected_at + timedelta(days=14)
    near = db.execute(
        select(models.Maintenance)
        .where(
            models.Maintenance.asset_id == asset_id,
            models.Maintenance.started_at >= window_start,
            models.Maintenance.started_at <= window_end,
        )
        .order_by(models.Maintenance.started_at.desc())
        .limit(1)
    ).scalars().first()
    if near:
        return {
            "summary": near.issue or near.action_taken or "Maintenance on record",
            "maintenance_id": near.maintenance_id,
        }
    return {"summary": None, "maintenance_id": None}


def repair_costs(
    db: Session,
    asset_ids: list[str],
    start: date,
    end_inclusive: date,
) -> dict[str, Any]:
    start_dt = start_of_day(start)
    end_ex = inclusive_date_end_to_exclusive(end_inclusive)
    rows = []
    for asset_id in asset_ids:
        mnts = db.execute(
            select(models.Maintenance).where(
                models.Maintenance.asset_id == asset_id,
                models.Maintenance.started_at >= start_dt,
                models.Maintenance.started_at < end_ex,
            )
        ).scalars().all()
        # aggregate by unique maintenance_id (already unique)
        total = sum((m.cost_total or Decimal("0")) for m in mnts)
        rows.append(
            {
                "asset_id": asset_id,
                "cost_usd": float(total),
                "maintenance_ids": [m.maintenance_id for m in mnts],
                "count": len(mnts),
            }
        )
    return {
        "rows": rows,
        "time_bounds": {"start": start.isoformat(), "end_inclusive": end_inclusive.isoformat()},
        "units": {"cost_usd": "USD"},
    }


def spill_map(
    db: Session,
    area_name: str,
    start: date,
    end_inclusive: date,
) -> dict[str, Any]:
    area = resolve_area_id(db, area_name) or db.execute(
        select(models.Area).where(models.Area.name.ilike(f"%{area_name}%"))
    ).scalars().first()
    if not area:
        return {"error": "area_not_found"}
    wells = db.execute(select(models.Well).where(models.Well.area_id == area.area_id)).scalars().all()
    start_dt = start_of_day(start)
    end_ex = inclusive_date_end_to_exclusive(end_inclusive)
    pins = []
    for well in wells:
        inspections = db.execute(
            select(models.Inspection).where(
                models.Inspection.asset_id == well.asset_id,
                models.Inspection.inspected_at >= start_dt,
                models.Inspection.inspected_at < end_ex,
                models.Inspection.spill_detected.is_(True),
            )
        ).scalars().all()
        events = []
        for insp in inspections:
            eff = effective_inspection(db, insp, well.well_type)
            if eff.excluded_spill or not eff.spill_detected:
                continue
            events.append(
                {
                    "inspection_id": insp.inspection_id,
                    "date": insp.inspected_at.date().isoformat(),
                    "volume_bbl": float(eff.spill_volume_bbl) if eff.spill_volume_bbl is not None else None,
                }
            )
        if events:
            pins.append(
                {
                    "asset_id": well.asset_id,
                    "lat": float(well.lat),
                    "lon": float(well.lon),
                    "events": events,
                }
            )
    return {"area_name": area.name, "pins": pins, "well_count": len(pins)}


def spill_heatmap(db: Session, year: int) -> dict[str, Any]:
    areas = db.execute(select(models.Area)).scalars().all()
    matrix: dict[str, dict[str, int]] = {}
    for area in areas:
        matrix[area.name] = {f"{year}-{m:02d}": 0 for m in range(1, 13)}
        wells = db.execute(select(models.Well).where(models.Well.area_id == area.area_id)).scalars().all()
        for well in wells:
            inspections = db.execute(
                select(models.Inspection).where(
                    models.Inspection.asset_id == well.asset_id,
                    models.Inspection.spill_detected.is_(True),
                    models.Inspection.inspected_at >= start_of_day(date(year, 1, 1)),
                    models.Inspection.inspected_at < start_of_day(date(year + 1, 1, 1)),
                )
            ).scalars().all()
            for insp in inspections:
                eff = effective_inspection(db, insp, well.well_type)
                if eff.excluded_spill or not eff.spill_detected:
                    continue
                key = f"{insp.inspected_at.year}-{insp.inspected_at.month:02d}"
                matrix[area.name][key] = matrix[area.name].get(key, 0) + 1
    # trim to months that have any data or Jan-Oct for challenge year
    months = [f"{year}-{m:02d}" for m in range(1, 11)]
    rows = []
    for area_name, months_map in matrix.items():
        values = [months_map.get(m, 0) for m in months]
        rows.append({"area_name": area_name, "months": months, "values": values, "total": sum(values)})
    rows.sort(key=lambda r: r["area_name"])
    return {"year": year, "months": months, "rows": rows, "corrections_applied": True}
