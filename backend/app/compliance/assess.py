from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.effective import effective_inspection
from app.db import models


def assess_containment_breaches(
    db: Session,
    *,
    area_name: str,
    start: datetime,
    end: datetime,
) -> dict:
    from app.analytics.queries import resolve_area_id

    area = resolve_area_id(db, area_name) or db.execute(
        select(models.Area).where(models.Area.name.ilike(f"%{area_name}%"))
    ).scalars().first()
    if not area:
        return {"error": "area_not_found"}

    wells = db.execute(select(models.Well).where(models.Well.area_id == area.area_id)).scalars().all()
    limit_h = Decimal("4")
    candidates = 0
    assessed = 0
    missing = 0
    breaches = []

    for well in wells:
        inspections = db.execute(
            select(models.Inspection).where(
                models.Inspection.asset_id == well.asset_id,
                models.Inspection.inspected_at >= start,
                models.Inspection.inspected_at <= end,
                models.Inspection.spill_detected.is_(True),
            )
        ).scalars().all()
        for insp in inspections:
            eff = effective_inspection(db, insp, well.well_type)
            if eff.excluded_spill or not eff.spill_detected:
                continue
            candidates += 1
            facts = db.execute(
                select(models.ExtractedFact).where(
                    models.ExtractedFact.inspection_id == insp.inspection_id,
                    models.ExtractedFact.fact_type == "containment_hours",
                )
            ).scalars().all()
            if not facts:
                # also try via maintenance link
                mnts = db.execute(
                    select(models.Maintenance).where(
                        models.Maintenance.triggered_by_inspection_id == insp.inspection_id
                    )
                ).scalars().all()
                for m in mnts:
                    facts.extend(
                        db.execute(
                            select(models.ExtractedFact).where(
                                models.ExtractedFact.maintenance_id == m.maintenance_id,
                                models.ExtractedFact.fact_type == "containment_hours",
                            )
                        ).scalars().all()
                    )
            if not facts:
                missing += 1
                continue
            assessed += 1
            fact = facts[0]
            hours = fact.value_numeric
            if hours is not None and hours > limit_h:
                breaches.append(
                    {
                        "asset_id": well.asset_id,
                        "inspection_id": insp.inspection_id,
                        "maintenance_id": fact.maintenance_id,
                        "containment_hours": float(hours),
                        "approximate": fact.approximate,
                        "limit_hours": float(limit_h),
                        "status": "exceeded",
                        "supporting_text": fact.supporting_text,
                        "report_path": fact.report_path,
                    }
                )

    return {
        "area_name": area.name,
        "protocol_id": "SR-02",
        "limit_hours": float(limit_h),
        "breaches": breaches,
        "coverage": {
            "candidate_count": candidates,
            "assessed_count": assessed,
            "missing_count": missing,
        },
    }


def assess_well_compliance(db: Session, asset_id: str, as_of: datetime, lookback_days: int = 365) -> dict:
    well = db.get(models.Well, asset_id)
    if not well:
        return {"error": "well_not_found"}
    start = as_of - timedelta(days=lookback_days)
    breaches = []
    pending = []
    satisfied = []
    potential = []

    events = db.execute(
        select(models.RegulatoryEvent).where(
            models.RegulatoryEvent.asset_id == asset_id,
            models.RegulatoryEvent.event_date >= start.date(),
        )
    ).scalars().all()

    fines_total = Decimal("0")
    for ev in events:
        if ev.fine_usd:
            fines_total += ev.fine_usd
        if ev.protocol_id == "SR-01" and ev.hours_to_report and ev.hours_to_report > 24:
            breaches.append(
                {
                    "protocol_id": "SR-01",
                    "status": "breached",
                    "detail": f"Reported after {ev.hours_to_report} hours",
                    "event_id": ev.event_id,
                    "fine_usd": float(ev.fine_usd) if ev.fine_usd else None,
                    "event_status": ev.status,
                }
            )
        if ev.event_type == "notice_of_violation":
            # RC-04: response within 30 days
            response = next(
                (
                    e
                    for e in events
                    if e.event_type == "nov_response_filed"
                    and e.related_inspection_id == ev.related_inspection_id
                ),
                None,
            )
            if not response:
                due = (ev.event_date + timedelta(days=30)) if ev.event_date else None
                if due and due < as_of.date():
                    breaches.append(
                        {
                            "protocol_id": "RC-04",
                            "status": "breached",
                            "detail": "No NOV response recorded",
                            "event_id": ev.event_id,
                            "due": due.isoformat(),
                        }
                    )
                elif due:
                    pending.append({"protocol_id": "RC-04", "due": due.isoformat(), "event_id": ev.event_id})

    # SR-02 from facts
    facts = db.execute(
        select(models.ExtractedFact).where(
            models.ExtractedFact.asset_id == asset_id,
            models.ExtractedFact.fact_type == "containment_hours",
        )
    ).scalars().all()
    for fact in facts:
        if fact.value_numeric and fact.value_numeric > 4:
            breaches.append(
                {
                    "protocol_id": "SR-02",
                    "status": "breached",
                    "detail": f"Contained after about {fact.value_numeric} hours",
                    "maintenance_id": fact.maintenance_id,
                    "supporting_text": fact.supporting_text,
                }
            )

    # SR-03 open site inspection pending
    for ev in events:
        if ev.event_type == "site_inspection" and ev.status == "open":
            breaches.append(
                {
                    "protocol_id": "SR-03",
                    "status": "breached",
                    "detail": "Cleanup verification still open",
                    "event_id": ev.event_id,
                }
            )

    # RC-02 annual flowline test
    tests = db.execute(
        select(models.Maintenance).where(
            models.Maintenance.asset_id == asset_id,
            models.Maintenance.issue.ilike("%Annual flowline integrity test%"),
            models.Maintenance.started_at >= datetime(as_of.year, 1, 1, tzinfo=as_of.tzinfo),
        )
    ).scalars().all()
    if tests:
        satisfied.append(
            {
                "protocol_id": "RC-02",
                "status": "met",
                "detail": f"Flowline test {tests[0].maintenance_id} on {tests[0].started_at.date()}",
            }
        )

    # RCA pending
    from app.analytics.rca import rca_threshold

    threshold, _ = rca_threshold(db, well.well_type)
    for kind in ["flowline", "pump_jack"]:
        mnts = db.execute(
            select(models.Maintenance).where(
                models.Maintenance.asset_id == asset_id,
                models.Maintenance.maintenance_type == "corrective",
                models.Maintenance.equipment_kind == kind,
                models.Maintenance.started_at >= start,
            )
        ).scalars().all()
        if len(mnts) >= threshold:
            pending.append(
                {
                    "protocol_id": "RCA",
                    "status": "pending",
                    "detail": f"{len(mnts)} corrective {kind} repairs in 12 months (threshold {threshold})",
                    "maintenance_ids": [m.maintenance_id for m in mnts],
                }
            )

    notes = db.execute(
        select(models.SourceNote).where(
            models.SourceNote.asset_id == asset_id,
            models.SourceNote.note_type.in_(["operator_feedback", "operator_note"]),
        )
    ).scalars().all()
    for n in notes:
        if "not yet in the maintenance system" in n.text.lower() or "work order not yet" in n.text.lower():
            pending.append(
                {
                    "protocol_id": "RECORDS",
                    "status": "pending_review",
                    "detail": "Planned shut-in not yet recorded in maintenance system",
                    "note_id": n.note_id,
                    "ambiguity": "Q9 pre-work documentation — see docs/decisions",
                }
            )

    # Deduplicate fines: unique event IDs with fines
    fine_events = {
        ev.event_id: float(ev.fine_usd)
        for ev in events
        if ev.fine_usd and ev.fine_usd > 0
    }

    return {
        "asset_id": asset_id,
        "as_of": as_of.isoformat(),
        "breaches": breaches,
        "potential_breaches": potential,
        "pending": pending,
        "satisfied": satisfied,
        "recorded_fines_usd": float(fines_total),
        "fine_events": fine_events,
    }
