from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.ingestion.hashing import content_hash, file_hash
from app.ingestion.rules_seed import RULES
from app.ingestion.report_facts import extract_facts_from_report


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _upsert_by_pk(db: Session, model, pk_field: str, pk: str, values: dict[str, Any]) -> str:
    existing = db.get(model, pk)
    if existing is None:
        db.add(model(**{pk_field: pk, **values}))
        return "inserted"
    old_hash = getattr(existing, "content_hash", None)
    new_hash = values.get("content_hash")
    if old_hash == new_hash:
        return "noop"
    for k, v in values.items():
        setattr(existing, k, v)
    return "updated"


def _safe_report_path(asset_dir: Path, report_file: str) -> Path | None:
    if not report_file:
        return None
    candidate = (asset_dir / report_file).resolve()
    try:
        candidate.relative_to(asset_dir.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def import_dataset(db: Session, source_root: Path, dataset_version: str = "sample-v1") -> dict[str, Any]:
    source_root = source_root.resolve()
    fleet = source_root / "fleet"
    assets = source_root / "assets"
    if not fleet.is_dir() or not assets.is_dir():
        raise FileNotFoundError(f"Expected fleet/ and assets/ under {source_root}")

    batch = models.ImportBatch(
        dataset_version=dataset_version,
        source_root=str(source_root),
        status="running",
    )
    db.add(batch)
    db.flush()

    counts: dict[str, int] = {
        "areas": 0,
        "teams": 0,
        "users": 0,
        "wells": 0,
        "inspections": 0,
        "maintenance": 0,
        "regulatory_events": 0,
        "source_notes": 0,
        "documents": 0,
        "extracted_facts": 0,
        "noop": 0,
        "updated": 0,
        "quarantine": 0,
        "unknown_refs": 0,
        "corrections_from_notes": 0,
        "parts_installed": 0,
    }
    unknown_refs: list[str] = []

    # Areas / teams
    areas_path = fleet / "areas.json"
    areas_data = json.loads(areas_path.read_text())
    for team in areas_data.get("teams", []):
        h = content_hash(team)
        action = _upsert_by_pk(
            db,
            models.Team,
            "team_id",
            team["team_id"],
            {
                "name": team["name"],
                "lead_user_id": team.get("lead_user_id"),
                "content_hash": h,
            },
        )
        counts["teams"] += 1 if action != "noop" else 0
        counts[action if action in ("noop", "updated") else "teams"] += 0
        if action == "noop":
            counts["noop"] += 1
        elif action == "updated":
            counts["updated"] += 1

    for area in areas_data.get("areas", []):
        h = content_hash(area)
        center = area.get("center") or {}
        action = _upsert_by_pk(
            db,
            models.Area,
            "area_id",
            area["area_id"],
            {
                "name": area["name"],
                "team_id": area["team_id"],
                "center_lat": _dec(center.get("lat")),
                "center_lon": _dec(center.get("lon")),
                "content_hash": h,
            },
        )
        if action == "inserted":
            counts["areas"] += 1
        elif action == "noop":
            counts["noop"] += 1
        else:
            counts["updated"] += 1

    users_path = fleet / "users.json"
    users_data = json.loads(users_path.read_text())
    for user in users_data.get("users", []):
        h = content_hash(user)
        action = _upsert_by_pk(
            db,
            models.User,
            "user_id",
            user["user_id"],
            {
                "name": user["name"],
                "role": user["role"],
                "team_id": user.get("team_id"),
                "content_hash": h,
            },
        )
        if action == "inserted":
            counts["users"] += 1
        elif action == "noop":
            counts["noop"] += 1
        else:
            counts["updated"] += 1

    # Seed rules
    for rule in RULES:
        existing = db.get(models.DomainRule, rule["rule_id"])
        if existing is None:
            db.add(models.DomainRule(**rule))
        else:
            for k, v in rule.items():
                setattr(existing, k, v)

    # Documents: all well-type manuals + all SOPs under fleet/ (profile-agnostic)
    doc_paths: list[Path] = []
    wt_dir = fleet / "well-types"
    sop_dir = fleet / "sops"
    if wt_dir.is_dir():
        doc_paths.extend(sorted(wt_dir.glob("*.md")))
    if sop_dir.is_dir():
        doc_paths.extend(sorted(sop_dir.glob("*.md")))
    for path in doc_paths:
        body = path.read_text(encoding="utf-8")
        h = file_hash(str(path))
        rel = str(path.relative_to(fleet))
        key = f"fleet/{rel}"
        existing = db.execute(select(models.Document).where(models.Document.doc_key == key)).scalar_one_or_none()
        if existing and existing.content_hash == h:
            counts["noop"] += 1
        elif existing:
            existing.body = body
            existing.content_hash = h
            counts["updated"] += 1
        else:
            doc = models.Document(
                doc_key=key,
                path=key,
                title=path.stem,
                content_hash=h,
                body=body,
                kind="manual" if "well-types" in rel else "sop",
            )
            db.add(doc)
            db.flush()
            parts = re.split(r"(?m)^## ", body)
            for i, part in enumerate(parts):
                text = part if i == 0 else "## " + part
                if text.strip():
                    db.add(
                        models.DocumentChunk(
                            document_id=doc.id,
                            section=text.split("\n", 1)[0][:250],
                            ordinal=i,
                            text=text[:8000],
                        )
                    )
            counts["documents"] += 1

    # Ensure knowledge version row
    kv = db.execute(select(models.KnowledgeVersion)).scalars().first()
    if kv is None:
        db.add(models.KnowledgeVersion(data_version=1, knowledge_version=1))

    well_dirs = sorted([p for p in assets.iterdir() if p.is_dir() and p.name.startswith("WELL-")])
    for well_dir in well_dirs:
        meta_path = well_dir / "metadata.json"
        if not meta_path.exists():
            db.add(
                models.QuarantineRow(
                    batch_id=batch.id,
                    source_path=str(meta_path),
                    reason="missing_metadata",
                )
            )
            counts["quarantine"] += 1
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError as exc:
            db.add(
                models.QuarantineRow(
                    batch_id=batch.id,
                    source_path=str(meta_path),
                    reason=f"invalid_json:{exc}",
                )
            )
            counts["quarantine"] += 1
            continue

        asset_id = meta["asset_id"]
        h = content_hash(meta)
        loc = meta.get("location") or {}
        action = _upsert_by_pk(
            db,
            models.Well,
            "asset_id",
            asset_id,
            {
                "name": meta.get("name", asset_id),
                "well_type": meta["well_type"],
                "area_id": meta["area_id"],
                "team_id": meta["team_id"],
                "in_charge_user_id": meta.get("in_charge_user_id"),
                "lat": _dec(loc.get("lat")) or Decimal("0"),
                "lon": _dec(loc.get("lon")) or Decimal("0"),
                "installed_on": _parse_date(meta.get("installed_on")),
                "recorded_status": meta.get("recorded_status"),
                "content_hash": h,
                "source_path": str(meta_path.relative_to(source_root)),
                "payload": meta,
            },
        )
        if action == "inserted":
            counts["wells"] += 1
        elif action == "noop":
            counts["noop"] += 1
        else:
            counts["updated"] += 1

        # equipment replace-lite
        existing_eq = db.execute(
            select(models.Equipment).where(models.Equipment.asset_id == asset_id)
        ).scalars().all()
        if not existing_eq:
            for eq in meta.get("equipment", []):
                db.add(
                    models.Equipment(
                        asset_id=asset_id,
                        equipment_id=eq["equipment_id"],
                        kind=eq["kind"],
                        model=eq.get("model"),
                    )
                )

        # inspections
        insp_path = well_dir / "inspections.jsonl"
        if insp_path.exists():
            for line_no, line in enumerate(insp_path.read_text().splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    db.add(
                        models.QuarantineRow(
                            batch_id=batch.id,
                            source_path=str(insp_path),
                            locator=str(line_no),
                            reason=f"invalid_json:{exc}",
                            payload={"line": line[:500]},
                        )
                    )
                    counts["quarantine"] += 1
                    continue
                iid = row["inspection_id"]
                h = content_hash(row)
                action = _upsert_by_pk(
                    db,
                    models.Inspection,
                    "inspection_id",
                    iid,
                    {
                        "asset_id": row["asset_id"],
                        "inspected_at": _parse_dt(row["inspected_at"]),
                        "inspector_user_id": row.get("inspector_user_id"),
                        "method": row.get("method"),
                        "ambient_temp_c": _dec(row.get("ambient_temp_c")),
                        "wellhead_temp_c": _dec(row.get("wellhead_temp_c")),
                        "spill_detected": row.get("spill_detected"),
                        "spill_area_pct": _dec(row.get("spill_area_pct")),
                        "spill_est_volume_bbl": _dec(row.get("spill_est_volume_bbl")),
                        "notes": row.get("notes"),
                        "evidence_images": row.get("evidence_images"),
                        "content_hash": h,
                        "source_path": str(insp_path.relative_to(source_root)),
                        "source_line": line_no,
                        "payload": row,
                    },
                )
                if action == "inserted":
                    counts["inspections"] += 1
                elif action == "noop":
                    counts["noop"] += 1
                else:
                    counts["updated"] += 1

        # maintenance
        mnt_path = well_dir / "maintenance.jsonl"
        if mnt_path.exists():
            for line_no, line in enumerate(mnt_path.read_text().splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    db.add(
                        models.QuarantineRow(
                            batch_id=batch.id,
                            source_path=str(mnt_path),
                            locator=str(line_no),
                            reason=f"invalid_json:{exc}",
                        )
                    )
                    counts["quarantine"] += 1
                    continue
                mid = row["maintenance_id"]
                cost = row.get("cost_usd") or {}
                h = content_hash(row)
                action = _upsert_by_pk(
                    db,
                    models.Maintenance,
                    "maintenance_id",
                    mid,
                    {
                        "asset_id": row["asset_id"],
                        "started_at": _parse_dt(row["started_at"]),
                        "completed_at": _parse_dt(row.get("completed_at")),
                        "maintenance_type": row.get("maintenance_type"),
                        "equipment_kind": row.get("equipment_kind"),
                        "issue": row.get("issue"),
                        "action_taken": row.get("action_taken"),
                        "technician_user_id": row.get("technician_user_id"),
                        "contractor": row.get("contractor"),
                        "downtime_hours": _dec(row.get("downtime_hours")),
                        "cost_labor": _dec(cost.get("labor")),
                        "cost_parts": _dec(cost.get("parts")),
                        "cost_total": _dec(cost.get("total")),
                        "triggered_by_inspection_id": row.get("triggered_by_inspection_id"),
                        "report_file": row.get("report_file"),
                        "content_hash": h,
                        "source_path": str(mnt_path.relative_to(source_root)),
                        "source_line": line_no,
                        "payload": row,
                    },
                )
                if action == "inserted":
                    counts["maintenance"] += 1
                elif action == "noop":
                    counts["noop"] += 1
                else:
                    counts["updated"] += 1

                report_rel = row.get("report_file")
                report_path = _safe_report_path(well_dir, report_rel) if report_rel else None
                if report_rel and report_path is None:
                    unknown_refs.append(f"missing_report:{asset_id}:{report_rel}")
                    counts["unknown_refs"] += 1
                elif report_path is not None:
                    body = report_path.read_text(encoding="utf-8")
                    key = f"{asset_id}/{report_rel}"
                    hdoc = file_hash(str(report_path))
                    existing = db.execute(
                        select(models.Document).where(models.Document.doc_key == key)
                    ).scalar_one_or_none()
                    if not existing:
                        doc = models.Document(
                            doc_key=key,
                            path=str(report_path.relative_to(source_root)),
                            title=mid,
                            content_hash=hdoc,
                            body=body,
                            kind="maintenance_report",
                        )
                        db.add(doc)
                        counts["documents"] += 1
                        facts = extract_facts_from_report(
                            body,
                            asset_id=asset_id,
                            maintenance_id=mid,
                            inspection_id=row.get("triggered_by_inspection_id"),
                            report_path=str(report_path.relative_to(source_root)),
                        )
                        for fact in facts:
                            db.add(models.ExtractedFact(**fact))
                            counts["extracted_facts"] += 1
                            if fact.get("fact_type") in {"parts_installed", "pump_lot"}:
                                counts["parts_installed"] += 1

        # regulatory
        reg_path = well_dir / "regulatory-events.jsonl"
        if reg_path.exists():
            for line_no, line in enumerate(reg_path.read_text().splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    counts["quarantine"] += 1
                    continue
                eid = row["event_id"]
                h = content_hash(row)
                action = _upsert_by_pk(
                    db,
                    models.RegulatoryEvent,
                    "event_id",
                    eid,
                    {
                        "asset_id": row.get("asset_id", asset_id),
                        "event_date": _parse_date(row.get("date")),
                        "agency": row.get("agency"),
                        "event_type": row.get("event_type"),
                        "protocol_id": row.get("protocol_id"),
                        "related_inspection_id": row.get("related_inspection_id"),
                        "hours_to_report": _dec(row.get("hours_to_report")),
                        "detail": row.get("detail"),
                        "fine_usd": _dec(row.get("fine_usd")),
                        "status": row.get("status"),
                        "content_hash": h,
                        "source_path": str(reg_path.relative_to(source_root)),
                        "payload": row,
                    },
                )
                if action == "inserted":
                    counts["regulatory_events"] += 1
                elif action == "noop":
                    counts["noop"] += 1
                else:
                    counts["updated"] += 1

        # context notes
        ctx_path = well_dir / "context.jsonl"
        if ctx_path.exists():
            for line_no, line in enumerate(ctx_path.read_text().splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    counts["quarantine"] += 1
                    continue
                nid = row["note_id"]
                h = content_hash(row)
                action = _upsert_by_pk(
                    db,
                    models.SourceNote,
                    "note_id",
                    nid,
                    {
                        "asset_id": row.get("asset_id", asset_id),
                        "created_at": _parse_dt(row["created_at"]),
                        "author_user_id": row.get("author_user_id"),
                        "note_type": row.get("note_type"),
                        "inspection_id": row.get("inspection_id"),
                        "text": row.get("text", ""),
                        "valid_from": _parse_date(row.get("valid_from")),
                        "valid_to": _parse_date(row.get("valid_to")),
                        "content_hash": h,
                        "source_path": str(ctx_path.relative_to(source_root)),
                        "payload": row,
                    },
                )
                if action == "inserted":
                    counts["source_notes"] += 1
                elif action == "noop":
                    counts["noop"] += 1
                else:
                    counts["updated"] += 1

                # Promote formal data_correction notes into the Correction table
                if row.get("note_type") == "data_correction" and row.get("inspection_id") and row.get("field"):
                    field = str(row["field"])
                    new_val = row.get("corrected_value")
                    if new_val is not None:
                        key = f"import:{nid}:{field}:{new_val}"
                        existing_c = (
                            db.query(models.Correction)
                            .filter(models.Correction.idempotency_key == key)
                            .first()
                        )
                        if existing_c is None:
                            for prior in (
                                db.query(models.Correction)
                                .filter(
                                    models.Correction.target_id == row["inspection_id"],
                                    models.Correction.field == field,
                                    models.Correction.status == "active",
                                )
                                .all()
                            ):
                                prior.status = "superseded"
                            db.add(
                                models.Correction(
                                    target_type="inspection",
                                    target_id=row["inspection_id"],
                                    field=field,
                                    original_value=(
                                        str(row["original_value"])
                                        if row.get("original_value") is not None
                                        else None
                                    ),
                                    new_value=str(new_val),
                                    unit=None,
                                    author_user_id=row.get("author_user_id") or "import",
                                    reason=row.get("text") or f"Source note {nid}",
                                    scope="inspection",
                                    status="active",
                                    idempotency_key=key,
                                )
                            )
                            counts["corrections_from_notes"] += 1

        db.commit()  # per-well checkpoint

    # bump data version
    kv = db.execute(select(models.KnowledgeVersion)).scalars().first()
    if kv:
        kv.data_version += 1

    batch.status = "succeeded"
    batch.finished_at = datetime.now(timezone.utc)
    batch.summary = {
        "counts": counts,
        "well_dirs": len(well_dirs),
        "unknown_refs_sample": unknown_refs[:50],
        "dataset_version": dataset_version,
    }
    db.commit()
    return batch.summary
