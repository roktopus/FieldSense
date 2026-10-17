"""Supplier recall + parts-installed algorithms."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db import models


def recalled_lots_from_docs(db: Session) -> tuple[set[str], str | None]:
    doc = (
        db.query(models.Document)
        .filter(models.Document.doc_key.like("%supplier-recall%"))
        .first()
    )
    if not doc:
        # Fallback: any SOP mentioning LOT-
        docs = db.query(models.Document).filter(models.Document.kind == "sop").all()
        for d in docs:
            if "recall" in (d.title or "").lower() or "recall" in d.body.lower()[:500]:
                doc = d
                break
    if not doc:
        return set(), None
    lots = set()
    in_section = False
    for line in doc.body.splitlines():
        if re.search(r"what is recalled|manufacturing lots", line, re.I):
            in_section = True
            continue
        if in_section and line.startswith("##"):
            break
        if in_section:
            for m in re.finditer(r"(LOT-[\w-]+)", line):
                lots.add(m.group(1).upper())
    # If section parsing failed, take LOT lines that look like a list under recall
    if not lots:
        for m in re.finditer(r"(LOT-[\w-]+)", doc.body):
            lots.add(m.group(1).upper())
        # Drop lots explicitly listed as not affected if we can
        not_aff = re.search(
            r"not affected[^\n]*?((?:LOT-[\w-]+(?:,|\s|and\s))+)",
            doc.body,
            re.I,
        )
        if not_aff:
            for m in re.finditer(r"(LOT-[\w-]+)", not_aff.group(1)):
                lots.discard(m.group(1).upper())
    return lots, doc.doc_key


def _install_events(db: Session) -> list[dict[str, Any]]:
    lots = (
        db.query(models.ExtractedFact)
        .filter(models.ExtractedFact.fact_type == "pump_lot")
        .all()
    )
    events: list[dict[str, Any]] = []
    for fact in lots:
        mnt = db.get(models.Maintenance, fact.maintenance_id) if fact.maintenance_id else None
        if not mnt:
            continue
        events.append(
            {
                "asset_id": fact.asset_id,
                "lot": (fact.value_text or "").upper(),
                "maintenance_id": mnt.maintenance_id,
                "started_at": mnt.started_at,
                "cost_total": float(mnt.cost_total) if mnt.cost_total is not None else None,
                "report_path": fact.report_path,
                "supporting_text": fact.supporting_text,
            }
        )
    events.sort(key=lambda e: e["started_at"] or datetime.min.replace(tzinfo=None))
    return events


def recalled_pumps_still_in_ground(
    db: Session,
    *,
    as_of: datetime,
    area_names: list[str] | None = None,
    team_id: str | None = None,
    include_assertions: bool = True,
) -> dict[str, Any]:
    recalled, doc_key = recalled_lots_from_docs(db)
    events = _install_events(db)

    # Latest install per well as of as_of
    latest: dict[str, dict[str, Any]] = {}
    for ev in events:
        if ev["started_at"] and ev["started_at"] > as_of:
            continue
        latest[ev["asset_id"]] = ev

    # Shared assertions: pump replaced (removes from list)
    replaced: dict[str, dict[str, Any]] = {}
    if include_assertions:
        asserts = (
            db.query(models.Assertion)
            .filter(
                models.Assertion.kind.in_(["pump_replaced", "equipment_replaced", "shared_note"]),
                models.Assertion.confirmation_state.in_(["active", "unconfirmed"]),
            )
            .all()
        )
        for a in asserts:
            if not a.asset_id:
                continue
            payload = a.payload or {}
            if a.kind == "pump_replaced" or payload.get("pump_replaced") or "swapped" in (a.text or "").lower() or "replaced" in (a.text or "").lower():
                if "pump" in (a.text or "").lower() or a.kind == "pump_replaced" or payload.get("pump_replaced"):
                    replaced[a.asset_id] = {
                        "by": a.author_user_id,
                        "text": a.text,
                        "state": a.confirmation_state,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }

    rows: list[dict[str, Any]] = []
    area_by_well: dict[str, models.Area] = {}
    for asset_id, ev in latest.items():
        if ev["lot"] not in recalled:
            continue
        if asset_id in replaced and replaced[asset_id]["state"] == "active":
            continue
        well = db.get(models.Well, asset_id)
        if not well:
            continue
        area = db.get(models.Area, well.area_id)
        area_by_well[asset_id] = area
        if area_names and (not area or area.name not in area_names):
            continue
        if team_id and well.team_id != team_id:
            continue
        provenance = [
            f"Install {ev['maintenance_id']} lot {ev['lot']} ({ev['supporting_text']})",
            f"Recall notice {doc_key}" if doc_key else "Recall notice",
        ]
        if asset_id in replaced:
            provenance.append(
                f"Unconfirmed replacement claim by {replaced[asset_id]['by']}: {replaced[asset_id]['text']}"
            )
        rows.append(
            {
                "asset_id": asset_id,
                "area_name": area.name if area else None,
                "lot": ev["lot"],
                "install_maintenance_id": ev["maintenance_id"],
                "install_date": ev["started_at"].date().isoformat() if ev["started_at"] else None,
                "cost_usd": ev["cost_total"],
                "provenance": "; ".join(provenance),
                "unconfirmed_claim": asset_id in replaced and replaced[asset_id]["state"] == "unconfirmed",
            }
        )

    rows.sort(key=lambda r: (r["area_name"] or "", r["asset_id"]))
    by_area: dict[str, int] = {}
    for r in rows:
        by_area[r["area_name"] or "?"] = by_area.get(r["area_name"] or "?", 0) + 1
    return {
        "count": len(rows),
        "rows": rows,
        "by_area": by_area,
        "recalled_lots": sorted(recalled),
        "recall_doc": doc_key,
    }
