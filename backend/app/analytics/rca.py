from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models


def rca_threshold(db: Session, well_type: str) -> tuple[int, str]:
    """Return (threshold, provenance). Team override for T350 may lower to 2."""
    override = db.execute(
        select(models.RuleOverride).where(
            models.RuleOverride.well_type == well_type,
            models.RuleOverride.metric == "rca_corrective_count",
            models.RuleOverride.status == "active",
        )
    ).scalars().first()
    if override:
        return int(override.value), f"team_rule:{override.author_user_id}"
    rule = db.get(models.DomainRule, f"{well_type}-RCA-EQ")
    if rule and rule.threshold is not None:
        return int(rule.threshold), f"manual:{rule.rule_id}"
    return 3, "manual:default"


def wells_needing_rca(
    db: Session,
    *,
    area_name: str,
    equipment_kind: str,
    as_of: datetime,
) -> dict:
    from app.analytics.queries import resolve_area_id

    area = resolve_area_id(db, area_name) or db.execute(
        select(models.Area).where(models.Area.name.ilike(f"%{area_name}%"))
    ).scalars().first()
    if not area:
        return {"error": "area_not_found"}
    window_start = as_of - timedelta(days=365)
    wells = db.execute(select(models.Well).where(models.Well.area_id == area.area_id)).scalars().all()
    rows = []
    for well in wells:
        threshold, provenance = rca_threshold(db, well.well_type)
        mnts = db.execute(
            select(models.Maintenance).where(
                models.Maintenance.asset_id == well.asset_id,
                models.Maintenance.maintenance_type == "corrective",
                models.Maintenance.equipment_kind == equipment_kind,
                models.Maintenance.started_at >= window_start,
                models.Maintenance.started_at <= as_of,
            )
        ).scalars().all()
        count = len(mnts)
        if count >= threshold:
            rows.append(
                {
                    "asset_id": well.asset_id,
                    "well_type": well.well_type,
                    "corrective_count": count,
                    "threshold": threshold,
                    "rule_provenance": provenance,
                    "maintenance_ids": [m.maintenance_id for m in mnts],
                }
            )
    rows.sort(key=lambda r: r["asset_id"])
    return {
        "area_name": area.name,
        "equipment_kind": equipment_kind,
        "as_of": as_of.isoformat(),
        "rows": rows,
        "note": "Team overrides attributed to author; baseline from manuals",
    }
