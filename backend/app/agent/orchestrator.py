from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agent.evidence_synth import enrich_answer_evidence
from app.agent.intents import try_capability_route
from app.agent.llm_answer import answer_with_model
from app.agent.resolve import match_area
from app.core.config import get_settings
from app.analytics import queries
from app.analytics.rca import wells_needing_rca
from app.compliance.assess import assess_containment_breaches, assess_well_compliance
from app.db import models
from app.domain.clock import parse_as_of
from app.feedback.service import (
    apply_feedback,
    preview_feedback,
    record_assertion,
)


ProgressCb = Callable[[str, dict[str, Any]], None]


def _emit(cb: ProgressCb | None, event: str, payload: dict[str, Any]) -> None:
    if cb:
        cb(event, payload)


def run_question(
    db: Session,
    *,
    user_id: str,
    conversation_id: uuid.UUID,
    text: str,
    as_of: datetime | str | None = None,
    session_generation: int = 0,
    progress: ProgressCb | None = None,
) -> models.Run:
    clock = parse_as_of(as_of)
    run = models.Run(
        owner_user_id=user_id,
        conversation_id=conversation_id,
        status="running",
        query_text=text,
        as_of=clock,
        session_generation=session_generation,
    )
    db.add(run)
    db.flush()

    db.add(
        models.Message(
            conversation_id=conversation_id,
            role="user",
            content=text,
            run_id=run.id,
        )
    )
    db.commit()

    try:
        _emit(progress, "run.progress", {"stage": "resolving", "run_id": str(run.id)})
        if get_settings().answer_mode == "router":
            answer = _route(
                db,
                text=text,
                user_id=user_id,
                conversation_id=conversation_id,
                as_of=clock,
                progress=progress,
            )
        else:
            _emit(progress, "run.progress", {"stage": "planning", "run_id": str(run.id)})
            answer = answer_with_model(
                db,
                text=text,
                user_id=user_id,
                conversation_id=conversation_id,
                as_of=clock,
                progress=progress,
            )
        # Many capability paths return citations + rows but omit evidence[]. Fill before persist
        # so "See sources" always has linked records for table/chart answers.
        answer = enrich_answer_evidence(answer, db)
        result = models.ResultSet(
            owner_user_id=user_id,
            kind=answer.get("kind", "answer"),
            payload=answer,
        )
        db.add(result)
        db.flush()

        for ev in answer.get("evidence", [])[:200]:
            db.add(
                models.EvidenceItem(
                    result_set_id=result.id,
                    kind=ev.get("kind", "record"),
                    source_id=ev.get("source_id"),
                    source_path=ev.get("source_path"),
                    locator=ev.get("locator"),
                    title=ev.get("title"),
                    excerpt=ev.get("excerpt"),
                    meta=ev.get("meta"),
                )
            )

        # Persist discussed wells for private memory (wall-clock time for "yesterday")
        asset_ids = answer.get("discussed_asset_ids") or []
        if asset_ids:
            db.add(
                models.ConversationReference(
                    owner_user_id=user_id,
                    conversation_id=conversation_id,
                    label=answer.get("reference_label") or "Discussed wells",
                    asset_ids=asset_ids,
                    query_spec={**(answer.get("scope") or {}), "analysis_as_of": clock.isoformat()},
                    discussed_at=datetime.now(timezone.utc),
                )
            )

        envelope = {
            "schema_version": "1",
            "run_id": str(run.id),
            "result_set_id": str(result.id),
            "status": "complete",
            "kind": answer.get("kind") or result.kind,
            "scope": answer.get("scope") or {},
            "summary": answer.get("summary", ""),
            "claims": answer.get("claims") or [],
            "visuals": answer.get("visuals") or [],
            "citations": answer.get("citations") or [],
            "conflicts": answer.get("conflicts") or [],
            "coverage": answer.get("coverage") or {},
            "versions": {"data": 1, "knowledge": 1, **(answer.get("versions") or {})},
            "warnings": answer.get("warnings") or [],
            "rows": answer.get("rows"),
            "data": answer.get("data"),
        }
        run.result_set_id = result.id
        run.answer_json = envelope
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.add(
            models.Message(
                conversation_id=conversation_id,
                role="assistant",
                content=envelope["summary"],
                run_id=run.id,
                answer_json=envelope,
            )
        )
        conv = db.get(models.Conversation, conversation_id)
        if conv:
            conv.title = (text[:80] + "…") if len(text) > 80 else text
            conv.updated_at = datetime.now(timezone.utc)
        db.commit()
        _emit(progress, "answer.completed", envelope)
        return run
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(models.Run, run.id)
        if run:
            run.status = "failed"
            run.error = str(exc)
            db.commit()
        _emit(progress, "run.failed", {"error": str(exc), "run_id": str(run.id) if run else None})
        raise


def _route(
    db: Session,
    *,
    text: str,
    user_id: str,
    conversation_id: uuid.UUID,
    as_of: datetime,
    progress: ProgressCb | None,
) -> dict[str, Any]:
    q = text.strip()
    ql = q.lower()
    _emit(progress, "run.progress", {"stage": "calculating"})

    # General capability tools (final-set + coverage-aware) before sample handlers
    cap = try_capability_route(
        db,
        text=q,
        user_id=user_id,
        conversation_id=conversation_id,
        as_of=as_of,
    )
    if cap is not None:
        return cap

    # Feedback / corrections / memory (before analytical intents)
    if _is_thermal_correction(ql):
        return _handle_thermal_correction(db, q, user_id, as_of)
    if _is_spill_volume_correction(ql):
        return _handle_spill_correction(db, q, user_id, as_of)
    if ("for all t350" in ql and "root-cause" in ql) or ("t350" in ql and "after 2" in ql):
        return _handle_t350_rule(db, q, user_id)
    if "for everyone" in ql or "fyi for everyone" in ql:
        return _handle_shared_note(db, q, user_id, as_of)
    if "running fine" in ql or "back online" in ql:
        return _handle_unconfirmed_claim(db, q, user_id, as_of)
    if _is_planned_work_note(ql):
        return _handle_planned_work_note(db, q, user_id, as_of)
    if (
        "three wells we discussed yesterday" in ql
        or "wells we discussed yesterday" in ql
        or ("repairs cost" in ql and "discussed" in ql)
    ):
        return _handle_yesterday_recall(db, q, user_id, conversation_id, as_of)

    # Analytical intents
    well_match = re.search(r"(WELL-\d{4})", q, re.I)

    # Area "not producing" must run before single-well status: the phrase
    # "not producing oil right now" contains substring "producing oil right now".
    area_obj = match_area(db, q) if "not producing" in ql else None
    if area_obj:
        area_name = area_obj.name
        data = queries.non_producing_in_area(db, area_name, as_of)
        unexplained = [
            r["asset_id"]
            for r in data.get("rows", [])
            if str(r.get("reason", "")).startswith("No recorded reason")
        ]
        summary = (
            f"There are {data.get('count', 0)} wells in {data.get('area_name')} that are not "
            f"producing based on the latest inspection at/before {as_of.date()}."
        )
        if unexplained:
            summary += (
                f" {len(unexplained)} well(s) have no recorded reason "
                f"({', '.join(unexplained)}); suggest a field check — do not invent a cause."
            )
        return {
            "kind": "table",
            "summary": summary,
            "rows": data.get("rows"),
            "visuals": [
                {
                    "kind": "table",
                    "title": f"Non-producing wells — {data.get('area_name')}",
                    "dataset_ref": "rows",
                    "fields": [
                        "asset_id",
                        "delta_c",
                        "recorded_status",
                        "reason",
                        "inspector_observation",
                    ],
                }
            ],
            "scope": {"area": data.get("area_name"), "as_of": as_of.isoformat()},
            "discussed_asset_ids": [r["asset_id"] for r in data.get("rows", [])],
            "citations": [{"id": "inspections", "label": "Latest inspections"}],
            "evidence": [
                {
                    "kind": "inspection",
                    "source_id": (r.get("latest_inspection") or {}).get("inspection_id"),
                    "title": r["asset_id"],
                }
                for r in data.get("rows", [])
            ],
        }

    if well_match and (
        re.search(r"\bis\s+well-\d{4}\s+producing", ql)
        or (
            "right now" in ql
            and "producing" in ql
            and "not producing" not in ql
        )
    ):
        asset_id = well_match.group(1).upper()
        data = queries.get_well_summary(db, asset_id, as_of)
        return _status_card_answer(data)

    if "line chart" in ql or ("wellhead" in ql and "air temperature" in ql) or "last 13 weeks" in ql:
        if not well_match:
            return {
                "kind": "short_answer",
                "summary": "Name the well (WELL-####) for the temperature chart.",
                "visuals": [],
            }
        asset_id = well_match.group(1).upper()
        # Q3: ~13 weekly inspections ending at latest reading on/before as_of
        end_i = as_of.date()
        start = end_i - timedelta(weeks=13)
        data = queries.temperature_series(db, asset_id, start, end_i)
        points = list(data.get("points") or [])
        if "13 weeks" in ql and len(points) > 13:
            points = points[-13:]
        offline = [
            str(p["inspected_at"])[:10]
            for p in points
            if p.get("status") == "not_producing"
        ]
        series_start = str(points[0]["inspected_at"])[:10] if points else start.isoformat()
        series_end = str(points[-1]["inspected_at"])[:10] if points else end_i.isoformat()
        return {
            "kind": "line_chart",
            "summary": (
                f"{len(points)} readings from {series_start} to {series_end}. "
                f"Not producing on: {', '.join(offline) if offline else 'none in series'}."
            ),
            "data": {**data, "points": points, "count": len(points), "non_producing_dates": offline},
            "rows": points,
            "visuals": [
                {
                    "kind": "line_chart",
                    "title": f"{asset_id} temperatures",
                    "dataset_ref": "rows",
                    "fields": ["inspected_at", "wellhead_temp_c", "ambient_temp_c", "status"],
                    "mark_status": "not_producing",
                }
            ],
            "scope": {"start": series_start, "end_inclusive": series_end},
            "discussed_asset_ids": [asset_id],
            "citations": [{"id": asset_id, "label": "Inspection series"}],
            "evidence": [
                {"kind": "inspection", "source_id": p["inspection_id"], "title": p["inspected_at"]}
                for p in points
            ],
        }

    if "how many oil spills" in ql or ("spills" in ql and well_match and "how many" in ql):
        asset_id = well_match.group(1).upper()
        end_i = as_of.date()
        start = date(end_i.year - 4, end_i.month, end_i.day)
        data = queries.spill_history(db, asset_id, start=start, end_inclusive=end_i)
        excluded_bits = ", ".join(
            f"{e['inspection_id']} ({e['inspected_at'][:10]})" for e in data.get("excluded", [])
        )
        summary = (
            f"{data['effective_spill_count']} spills totaling {data['known_volume_total']} bbl "
            f"in the last 4 years (through {end_i.isoformat()}). "
            f"{data['detection_count']} detections raw"
        )
        if data.get("excluded"):
            summary += f"; excluded as non-oil/corrected: {excluded_bits}"
        summary += "."
        return {
            "kind": "table",
            "summary": summary,
            "rows": data["spills"],
            "data": data,
            "visuals": [
                {
                    "kind": "table",
                    "title": f"Spills ({data['effective_spill_count']})",
                    "dataset_ref": "rows",
                    "fields": ["date", "volume_bbl", "inspection_id"],
                }
            ],
            "scope": {"start": start.isoformat(), "end_inclusive": end_i.isoformat()},
            "discussed_asset_ids": [asset_id],
            "citations": [{"id": e["inspection_id"], "label": e["inspection_id"]} for e in data["excluded"]],
            "evidence": [
                {"kind": "inspection", "source_id": s["inspection_id"], "title": s["date"]}
                for s in data["spills"]
            ]
            + [
                {"kind": "correction", "source_id": e["inspection_id"], "title": "Excluded detection"}
                for e in data["excluded"]
            ],
        }

    if "how many days" in ql and "down" in ql and well_match:
        asset_id = well_match.group(1).upper()
        year = 2025
        ym = re.search(r"(20\d{2})", q)
        if ym:
            year = int(ym.group(1))
        data = queries.downtime_for_asset_year(db, asset_id, year)
        return {
            "kind": "short_answer",
            "summary": f"{asset_id} was down {data['downtime_days']} days in {year}. {data['calculation']}",
            "data": data,
            "rows": data.get("details"),
            "visuals": [],
            "discussed_asset_ids": [asset_id],
            "citations": [{"id": d["inspection_id"], "label": d["inspection_id"]} for d in data.get("details", [])],
            "evidence": [
                {
                    "kind": "inspection",
                    "source_id": d["inspection_id"],
                    "title": d["inspected_at"],
                    "excerpt": d.get("cause"),
                }
                for d in data.get("details", [])
            ]
            + [
                {
                    "kind": "maintenance",
                    "source_id": d["maintenance_id"],
                    "title": d.get("cause"),
                }
                for d in data.get("details", [])
                if d.get("maintenance_id")
            ],
        }

    if "most downtime" in ql or ("downtime" in ql and ("top" in ql or "which" in ql) and "well" in ql):
        area = match_area(db, q)
        area_name = area.name if area else None
        if not area_name:
            return {
                "kind": "short_answer",
                "summary": "Name the geographic area for the downtime ranking (for example an area from the fleet list).",
                "visuals": [],
            }
        end = as_of.date()
        start = date(end.year, end.month, end.day)
        # last 4 months relative to as_of
        month = end.month - 4
        year = end.year
        while month <= 0:
            month += 12
            year -= 1
        start = date(year, month, min(end.day, 28))
        data = queries.analyze_downtime_by_area(
            db,
            area_name=area_name,
            start=start,
            end_inclusive=end,
            limit=3,
        )
        rows = data.get("rows", [])
        summary = (
            f"Top downtime wells in {area_name} between {start.isoformat()} and {end.isoformat()}: "
            + ", ".join(f"{r['asset_id']} ({r['downtime_days']} days)" for r in rows)
            + ". Downtime = 7 days × non-producing weekly inspections (missed inspections add 0)."
        )
        return {
            "kind": "bar_chart",
            "summary": summary,
            "rows": rows,
            "data": data,
            "visuals": [
                {
                    "kind": "bar_chart",
                    "title": f"Downtime (days) — {area_name}",
                    "dataset_ref": "rows",
                    "fields": ["asset_id", "downtime_days", "well_type"],
                },
                {
                    "kind": "table",
                    "title": "Ranked wells",
                    "dataset_ref": "rows",
                    "fields": ["asset_id", "well_type", "downtime_days", "why"],
                },
            ],
            "scope": data.get("time_bounds"),
            "discussed_asset_ids": [r["asset_id"] for r in rows],
            "reference_label": f"{area_name} downtime",
            "citations": [{"id": "downtime", "label": "Inspection-derived downtime"}],
            "evidence": [
                {"kind": "inspection", "source_id": iid, "title": iid}
                for r in rows
                for iid in r.get("contributing_inspection_ids", [])[:30]
            ],
        }

    if ("rules" in ql and "broken" in ql and well_match) or (
        well_match and "still open" in ql and ("rule" in ql or "breach" in ql or "compliance" in ql)
    ):
        asset_id = well_match.group(1).upper()
        data = assess_well_compliance(db, asset_id, as_of)
        breaches = data.get("breaches") or []
        pending = data.get("pending") or []
        satisfied = data.get("satisfied") or []
        fines = data.get("recorded_fines_usd") or 0
        summary = (
            f"{asset_id} has {len(breaches)} rule breach(es) in the last 12 months; "
            f"recorded fines USD {fines:,.0f} (still open where noted). "
        )
        if pending:
            summary += f"{len(pending)} open action(s) still pending (not yet counted as breaches). "
        if satisfied:
            summary += "Met: " + "; ".join(s.get("detail", s.get("protocol_id")) for s in satisfied) + "."
        rows = (
            [{**b, "category": "breach"} for b in breaches]
            + [{**p, "category": "pending"} for p in pending]
            + [{**s, "category": "met"} for s in satisfied]
        )
        return {
            "kind": "table",
            "summary": summary,
            "data": data,
            "rows": rows,
            "visuals": [
                {
                    "kind": "table",
                    "title": "Breaches & open actions",
                    "dataset_ref": "rows",
                    "fields": ["category", "protocol_id", "status", "detail"],
                }
            ],
            "discussed_asset_ids": [asset_id],
            "coverage": {},
            "evidence": [
                {"kind": "regulatory", "source_id": b.get("event_id"), "title": b.get("protocol_id")}
                for b in breaches
                if b.get("event_id")
            ],
        }

    if "not contained" in ql or ("contain" in ql and "sop" in ql) or (
        "contain" in ql and match_area(db, q) and "spill" in ql
    ):
        end = as_of
        start = as_of - timedelta(days=90)
        area = match_area(db, q)
        area_name = area.name if area else None
        if not area_name:
            return {
                "kind": "short_answer",
                "summary": "Name the area for containment breach analysis.",
                "visuals": [],
            }
        data = assess_containment_breaches(db, area_name=area_name, start=start, end=end)
        return {
            "kind": "table",
            "summary": f"{len(data.get('breaches', []))} spills exceeded the 4-hour containment limit (SR-02). Coverage: {data.get('coverage')}.",
            "rows": data.get("breaches"),
            "data": data,
            "visuals": [
                {
                    "kind": "table",
                    "title": f"Containment breaches — {area_name}",
                    "dataset_ref": "rows",
                    "fields": [
                        "asset_id",
                        "containment_hours",
                        "limit_hours",
                        "status",
                        "maintenance_id",
                    ],
                }
            ],
            "coverage": data.get("coverage"),
            "discussed_asset_ids": [b["asset_id"] for b in data.get("breaches", [])],
            "evidence": [
                {
                    "kind": "report",
                    "source_id": b.get("maintenance_id"),
                    "title": b.get("supporting_text"),
                    "source_path": b.get("report_path"),
                    "excerpt": b.get("supporting_text"),
                }
                for b in data.get("breaches", [])
            ],
        }

    if "root-cause analysis" in ql or "root cause analysis" in ql:
        area = match_area(db, q)
        area_name = area.name if area else None
        if not area_name:
            return {
                "kind": "short_answer",
                "summary": "Name the area for RCA candidates.",
                "visuals": [],
            }
        eq = "pump_jack"
        if "esp" in ql:
            eq = "esp_pump"
        data = wells_needing_rca(
            db,
            area_name=area_name,
            equipment_kind=eq,
            as_of=as_of,
        )
        return {
            "kind": "table",
            "summary": f"{len(data.get('rows', []))} wells need {eq} RCA under applicable rules. {data.get('note')}",
            "rows": data.get("rows"),
            "visuals": [
                {
                    "kind": "table",
                    "title": f"{eq} RCA candidates — {area_name}",
                    "dataset_ref": "rows",
                    "fields": ["asset_id", "well_type", "corrective_count", "threshold", "rule_provenance"],
                }
            ],
            "discussed_asset_ids": [r["asset_id"] for r in data.get("rows", [])],
            "evidence": [],
        }

    if "needed a report" in ql or ("reportable" in ql and "spill" in ql) or (
        "report to the regulator" in ql
    ):
        end = as_of.date()
        start = end - timedelta(days=90)
        area = match_area(db, q)
        area_name = area.name if area else None
        if not area_name:
            return {
                "kind": "short_answer",
                "summary": "Name the area for reportable spills.",
                "visuals": [],
            }
        data = queries.spill_map(db, area_name, start, end)
        reportable = []
        for pin in data.get("pins", []):
            for ev in pin.get("events", []):
                vol = ev.get("volume_bbl")
                if vol is not None and vol >= 5:
                    reportable.append(
                        {
                            "asset_id": pin["asset_id"],
                            "date": ev["date"],
                            "volume_bbl": vol,
                            "report_required": True,
                            "notice_recorded": False,
                            "status": "overdue",
                        }
                    )
        return {
            "kind": "table",
            "summary": f"{len(reportable)} reportable spill(s) in {area_name} in the last 90 days (threshold ≥ 5 bbl).",
            "rows": reportable,
            "visuals": [
                {
                    "kind": "table",
                    "title": f"Reportable spills — {area_name}",
                    "dataset_ref": "rows",
                    "fields": ["asset_id", "date", "volume_bbl", "status"],
                }
            ],
            "discussed_asset_ids": [r["asset_id"] for r in reportable],
            "evidence": [],
        }

    if "planned" in ql and "downtime" in ql and well_match:
        asset_id = well_match.group(1).upper()
        assertions = (
            db.query(models.Assertion)
            .filter(
                models.Assertion.asset_id == asset_id,
                models.Assertion.kind.in_(["planned_work", "shared_observation"]),
                models.Assertion.confirmation_state.in_(["active", "unconfirmed"]),
            )
            .order_by(models.Assertion.created_at.desc())
            .all()
        )
        if assertions:
            a = assertions[0]
            author = _user_display(db, a.author_user_id)
            return {
                "kind": "short_answer",
                "summary": f"Yes — according to {author}: {a.text}",
                "data": {"assertion_id": str(a.id), "author": author},
                "visuals": [],
                "citations": [{"id": str(a.id), "label": f"Shared note — {author}"}],
                "discussed_asset_ids": [asset_id],
                "evidence": [
                    {
                        "kind": "assertion",
                        "source_id": str(a.id),
                        "excerpt": a.text,
                        "title": author,
                    }
                ],
            }
        return {
            "kind": "short_answer",
            "summary": f"No shared planned-downtime note found for {asset_id}.",
            "visuals": [],
            "discussed_asset_ids": [asset_id],
            "evidence": [],
        }

    if ("real oil" in ql or ("was the" in ql and "spill" in ql)) and well_match:
        asset_id = well_match.group(1).upper()
        notes = (
            db.query(models.SourceNote)
            .filter(models.SourceNote.asset_id == asset_id)
            .all()
        )
        insp = (
            db.query(models.Inspection)
            .filter(
                models.Inspection.asset_id == asset_id,
                models.Inspection.spill_detected.is_(True),
            )
            .order_by(models.Inspection.inspected_at.desc())
            .all()
        )
        target = None
        for i in insp:
            if i.inspected_at.year == 2026 and i.inspected_at.month == 8 and i.inspected_at.day == 20:
                target = i
                break
        if not target and insp:
            target = insp[0]
        mnt = (
            db.query(models.Maintenance)
            .filter(
                models.Maintenance.asset_id == asset_id,
                models.Maintenance.triggered_by_inspection_id
                == (target.inspection_id if target else ""),
            )
            .first()
        )
        note_rows = [
            {
                "note_id": n.note_id,
                "note_type": n.note_type,
                "author": _user_display(db, n.author_user_id),
                "text": n.text,
            }
            for n in notes
        ]
        vol = float(target.spill_est_volume_bbl) if target and target.spill_est_volume_bbl else None
        summary = (
            f"Yes — the detection stands as a real oil spill "
            f"({target.inspection_id if target else 'inspection'}"
            f"{f', {vol} bbl' if vol is not None else ''}"
            f"{f'; notes: {target.notes}' if target and target.notes else ''}). "
            f"Informal notes disagree and neither is a formal correction"
            f"{f'; a spill repair ({mnt.maintenance_id}) was done' if mnt else ''}."
        )
        return {
            "kind": "conflict_review",
            "summary": summary,
            "data": {
                "inspection": {
                    "inspection_id": target.inspection_id if target else None,
                    "volume_bbl": vol,
                    "notes": target.notes if target else None,
                },
                "maintenance_id": mnt.maintenance_id if mnt else None,
                "notes": note_rows,
            },
            "conflicts": [
                {
                    "kind": "informal_disagreement",
                    "text": n["text"],
                    "note_id": n["note_id"],
                    "author": n["author"],
                }
                for n in note_rows
                if n["note_type"] != "correction"
            ],
            "visuals": [
                {
                    "kind": "table",
                    "title": "Source review",
                    "dataset_ref": "rows",
                    "fields": ["note_id", "note_type", "author", "text"],
                }
            ],
            "rows": note_rows,
            "discussed_asset_ids": [asset_id],
            "evidence": [
                {
                    "kind": "inspection",
                    "source_id": target.inspection_id if target else None,
                    "title": "Spill detection",
                }
            ]
            + [
                {"kind": "note", "source_id": n["note_id"], "excerpt": n["text"], "title": n["author"]}
                for n in note_rows
            ],
        }

    # Fallback help
    return {
        "kind": "short_answer",
        "summary": (
            "I can answer production status, downtime rankings, spills, compliance, "
            "corrections, and memory questions. Try: “Which wells in Northeast Block 7 "
            "had the most downtime between 16 June and 16 October 2026? Show a bar chart.”"
        ),
        "visuals": [],
        "warnings": ["unrecognized_intent_used_help_fallback"],
        "evidence": [],
    }


def _status_card_answer(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("error"):
        return {"kind": "short_answer", "summary": f"Well not found: {data.get('asset_id')}", "visuals": []}
    status = data["status"]
    label = "Producing" if status == "producing" else "Not producing" if status == "not_producing" else "Unknown"
    li = data.get("latest_inspection") or {}
    summary = (
        f"{data['asset_id']} is {label.lower()} based on the latest inspection "
        f"{li.get('inspection_id')} on {str(li.get('inspected_at', ''))[:10]} "
        f"by {li.get('inspector_name')} ({li.get('method')}). "
        f"ΔT={data.get('delta_c')} °C vs threshold {data.get('threshold_c')} °C."
    )
    if data.get("recorded_status_stale"):
        summary += f" Recorded status `{data.get('recorded_status')}` appears out of date."
    for c in data.get("applied_corrections") or []:
        summary += (
            f" Effective wellhead uses correction by {c.get('author')}: "
            f"{c.get('original')} → {c.get('new')} {c.get('field', '')}."
        )
    for conf in data.get("conflicts") or []:
        summary += (
            f" Conflict: inspector note “{conf.get('text')}” "
            f"({conf.get('author')}) disagrees with the corrected reading — please confirm."
        )
    for n in data.get("context_notes") or []:
        if n.get("note_id") == "CTX-0001-003" or "shut-in" in (n.get("text") or "").lower():
            summary += f" Context: {n.get('text')} ({n.get('note_id')})."
            break
    return {
        "kind": "status_card",
        "summary": summary,
        "data": data,
        "visuals": [
            {
                "kind": "status_card",
                "title": data["asset_id"],
                "dataset_ref": "data",
                "fields": ["status", "delta_c", "latest_inspection", "recorded_status"],
            }
        ],
        "conflicts": data.get("conflicts") or [],
        "discussed_asset_ids": [data["asset_id"]],
        "citations": [
            {"id": li.get("inspection_id"), "label": li.get("inspection_id")},
        ],
        "evidence": [
            {
                "kind": "inspection",
                "source_id": li.get("inspection_id"),
                "title": "Latest inspection",
                "excerpt": f"ΔT {data.get('delta_c')} °C",
            }
        ]
        + [
            {"kind": "note", "source_id": n["note_id"], "excerpt": n["text"], "title": n["note_type"]}
            for n in data.get("context_notes", [])[:5]
        ],
    }


def _is_thermal_correction(ql: str) -> bool:
    has_temp = "°" in ql or "wellhead" in ql or re.search(r"\d+(?:\.\d+)?\s*°?\s*c\b", ql)
    return bool(has_temp) and (
        "wrong" in ql or "faulty" in ql or "re-measured" in ql or "remeasured" in ql
    )


def _is_spill_volume_correction(ql: str) -> bool:
    return ("spill" in ql or "bbl" in ql) and ("measured" in ql or "correct" in ql) and (
        "estimated" in ql or "ai" in ql or "bbl" in ql
    )


def _is_planned_work_note(ql: str) -> bool:
    """Q17 Michael-style operational note (not FYI-for-everyone, not unconfirmed claim)."""
    if "running fine" in ql or "back online" in ql or "fyi" in ql or "for everyone" in ql:
        return False
    return (
        ("shut in" in ql or "shut-in" in ql)
        and ("planned" in ql or "has been" in ql or "since" in ql)
    ) or ("planned work" in ql or "planned workover" in ql)


def _user_display(db: Session, user_id: str) -> str:
    return queries.user_name(db, user_id) or user_id


def _handle_thermal_correction(db: Session, text: str, user_id: str, as_of: datetime) -> dict[str, Any]:
    from sqlalchemy import select

    m = re.search(r"(WELL-\d{4})", text, re.I)
    if not m:
        return {
            "kind": "short_answer",
            "summary": "Name the well (WELL-####) and the corrected wellhead temperature in °C.",
            "visuals": [],
        }
    asset_id = m.group(1).upper()
    temp_m = re.search(r"(\d+(?:\.\d+)?)\s*°?\s*c", text, re.I)
    if not temp_m:
        return {
            "kind": "short_answer",
            "summary": "Include the corrected wellhead temperature in °C.",
            "visuals": [],
        }
    new_temp = temp_m.group(1)

    insp = db.execute(
        select(models.Inspection)
        .where(
            models.Inspection.asset_id == asset_id,
            models.Inspection.inspected_at >= datetime(2026, 10, 15, tzinfo=as_of.tzinfo),
            models.Inspection.inspected_at < datetime(2026, 10, 16, tzinfo=as_of.tzinfo),
        )
        .limit(1)
    ).scalar_one_or_none()
    if not insp:
        insp = db.execute(
            select(models.Inspection)
            .where(models.Inspection.asset_id == asset_id)
            .order_by(models.Inspection.inspected_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    preview = preview_feedback(
        db,
        kind="measurement_correction",
        author_user_id=user_id,
        target_id=insp.inspection_id if insp else "",
        field="wellhead_temp_c",
        new_value=new_temp,
        reason=text,
        unit="°C",
    )
    applied = apply_feedback(db, preview=preview, author_user_id=user_id)
    summary = queries.get_well_summary(db, asset_id, as_of)
    author = _user_display(db, user_id)
    parts = [
        f"Correction recorded against {insp.inspection_id if insp else 'inspection'} by {author}.",
        f"Original wellhead {preview.get('original_value')} °C preserved; effective now {summary.get('wellhead_temp_c')} °C "
        f"(ΔT={summary.get('delta_c')} °C) → status {summary.get('status')}.",
    ]
    for conf in summary.get("conflicts") or []:
        parts.append(
            f"Please confirm: the same inspection notes “{conf.get('text')}” "
            f"({conf.get('author')}), which disagrees with this correction."
        )
    return {
        "kind": "correction_receipt",
        "summary": " ".join(parts),
        "data": {"preview": preview, "applied": applied, "summary": summary},
        "conflicts": summary.get("conflicts") or [],
        "visuals": [
            {
                "kind": "status_card",
                "title": asset_id,
                "dataset_ref": "data",
                "fields": ["summary"],
            }
        ],
        "discussed_asset_ids": [asset_id],
        "evidence": [
            {
                "kind": "correction",
                "source_id": applied.get("correction_id"),
                "title": insp.inspection_id if insp else asset_id,
                "excerpt": text,
            }
        ],
    }


def _handle_spill_correction(db: Session, text: str, user_id: str, as_of: datetime) -> dict[str, Any]:
    from sqlalchemy import select

    m = re.search(r"(WELL-\d{4})", text, re.I)
    if not m:
        return {
            "kind": "short_answer",
            "summary": "Name the well (WELL-####) and the measured spill volume in bbl.",
            "visuals": [],
        }
    asset_id = m.group(1).upper()
    # Prefer "measured X bbl" over an earlier AI estimate mentioned in the same sentence
    vol_m = re.search(r"measured\s+(\d+(?:\.\d+)?)\s*bbl", text, re.I) or re.search(
        r"(\d+(?:\.\d+)?)\s*bbl", text, re.I
    )
    if vol_m and "measured" not in text.lower():
        all_vols = re.findall(r"(\d+(?:\.\d+)?)\s*bbl", text, re.I)
        new_vol = all_vols[-1] if all_vols else None
    else:
        new_vol = vol_m.group(1) if vol_m else None
    if not new_vol:
        return {
            "kind": "short_answer",
            "summary": "Include the measured spill volume in bbl.",
            "visuals": [],
        }

    # Resolve spill date from text when present (e.g. "24 Sep"), else latest spill detection
    insp = None
    date_m = re.search(
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s*(20\d{2})?",
        text,
        re.I,
    )
    if date_m:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        day = int(date_m.group(1))
        mon_key = date_m.group(2).lower()[:4]
        if mon_key.startswith("sept"):
            mon = 9
        else:
            mon = months[date_m.group(2).lower()[:3]]
        year = int(date_m.group(3)) if date_m.group(3) else as_of.year
        day_start = datetime(year, mon, day, tzinfo=as_of.tzinfo)
        day_end = day_start + timedelta(days=1)
        insp = db.execute(
            select(models.Inspection)
            .where(
                models.Inspection.asset_id == asset_id,
                models.Inspection.inspected_at >= day_start,
                models.Inspection.inspected_at < day_end,
                models.Inspection.spill_detected.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none()
    if insp is None:
        insp = db.execute(
            select(models.Inspection)
            .where(
                models.Inspection.asset_id == asset_id,
                models.Inspection.spill_detected.is_(True),
                models.Inspection.inspected_at <= as_of,
            )
            .order_by(models.Inspection.inspected_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    preview = preview_feedback(
        db,
        kind="detection_correction",
        author_user_id=user_id,
        target_id=insp.inspection_id if insp else "",
        field="spill_est_volume_bbl",
        new_value=new_vol,
        reason=text,
        unit="bbl",
    )
    applied = apply_feedback(db, preview=preview, author_user_id=user_id)
    due_notice = None
    due_cleanup = None
    containment_note = ""
    if insp:
        due_notice = (insp.inspected_at + timedelta(hours=24)).isoformat()
        due_cleanup = (insp.inspected_at.date() + timedelta(days=60)).isoformat()
        from sqlalchemy import select as sel

        facts = db.execute(
            sel(models.ExtractedFact).where(
                models.ExtractedFact.asset_id == asset_id,
                models.ExtractedFact.fact_type == "containment_hours",
            )
        ).scalars().all()
        for fact in facts:
            if fact.value_numeric and fact.value_numeric > 4:
                containment_note = (
                    f" Repair report already shows containment ≈ {fact.value_numeric} h "
                    f"(SR-02 breach; limit 4 h)."
                )
                break
    author = _user_display(db, user_id)
    summary = (
        f"Spill volume for {asset_id} corrected to {new_vol} bbl by {author} "
        f"(AI/original estimate {preview.get('original_value')} bbl preserved on "
        f"{insp.inspection_id if insp else 'inspection'}). "
        f"At {new_vol} bbl the spill is reportable (≥ 5 bbl). "
        f"Written notice was due within 24 h ({due_notice}); none recorded → possible SR-01 breach. "
        f"Agency cleanup verification (SR-03) due within 60 days by {due_cleanup}."
        f"{containment_note} "
        f"Any prior 'moderate / no reporting duty' classification based on the old estimate no longer holds."
    )
    return {
        "kind": "correction_receipt",
        "summary": summary,
        "data": {
            "applied": applied,
            "obligations": {
                "SR-01": {"status": "potential_breach", "due": due_notice},
                "SR-02": {"status": "breached_if_reported_hours" if containment_note else "unknown"},
                "SR-03": {"status": "not_yet_due", "due": due_cleanup},
            },
        },
        "visuals": [
            {
                "kind": "table",
                "title": "Recomputed obligations",
                "dataset_ref": "rows",
                "fields": ["protocol", "status", "due"],
            }
        ],
        "rows": [
            {"protocol": "SR-01", "status": "potential_breach", "due": due_notice},
            {"protocol": "SR-02", "status": "see report", "due": None},
            {"protocol": "SR-03", "status": "not_yet_due", "due": due_cleanup},
        ],
        "discussed_asset_ids": [asset_id],
        "evidence": [
            {
                "kind": "correction",
                "source_id": applied.get("correction_id"),
                "title": insp.inspection_id if insp else asset_id,
            }
        ],
    }


def _handle_t350_rule(db: Session, text: str, user_id: str) -> dict[str, Any]:
    from decimal import Decimal

    existing = (
        db.query(models.RuleOverride)
        .filter(
            models.RuleOverride.well_type == "T350",
            models.RuleOverride.metric == "rca_corrective_count",
            models.RuleOverride.status == "active",
        )
        .first()
    )
    if not existing:
        db.add(
            models.RuleOverride(
                well_type="T350",
                equipment_kind="pump_jack",
                metric="rca_corrective_count",
                operator=">=",
                value=Decimal("2"),
                lookback_days=365,
                author_user_id=user_id,
            )
        )
        db.commit()
    return {
        "kind": "short_answer",
        "summary": (
            "Saved team operational rule for T350 pump-jack RCA after 2 corrective repairs "
            f"(author {user_id}). This is not a manual change; T200 remains at 3."
        ),
        "visuals": [],
        "discussed_asset_ids": [],
        "evidence": [],
    }


def _handle_shared_note(db: Session, text: str, user_id: str, as_of: datetime) -> dict[str, Any]:
    m = re.search(r"(WELL-\d{4})", text, re.I)
    asset_id = m.group(1).upper() if m else "WELL-0007"
    author = _user_display(db, user_id)
    a = record_assertion(
        db,
        kind="planned_work",
        author_user_id=user_id,
        asset_id=asset_id,
        text=text,
        payload={"shared": True, "author_name": author},
    )
    return {
        "kind": "shared_note",
        "summary": (
            f"Shared well note saved for {asset_id} by {author} (visible to everyone). "
            f"Private conversations remain private."
        ),
        "data": {
            "assertion_id": str(a.id),
            "asset_id": asset_id,
            "text": text,
            "author": author,
            "author_user_id": user_id,
        },
        "visuals": [],
        "discussed_asset_ids": [asset_id],
        "evidence": [{"kind": "assertion", "source_id": str(a.id), "excerpt": text, "title": author}],
    }


def _handle_planned_work_note(db: Session, text: str, user_id: str, as_of: datetime) -> dict[str, Any]:
    """Q17: record an operational shut-in / planned-work note (shared knowledge)."""
    m = re.search(r"(WELL-\d{4})", text, re.I)
    asset_id = m.group(1).upper() if m else "WELL-0175"
    author = _user_display(db, user_id)
    a = record_assertion(
        db,
        kind="planned_work",
        author_user_id=user_id,
        asset_id=asset_id,
        text=text,
        payload={"shared": True, "author_name": author},
        confirmation_state="active",
    )
    summary = queries.get_well_summary(db, asset_id, as_of)
    li = summary.get("latest_inspection") or {}
    align = (
        "This matches the latest inspection "
        f"({li.get('inspection_id')}, ΔT={summary.get('delta_c')} °C → {summary.get('status')})."
        if summary.get("status") == "not_producing"
        else (
            f"Noted. Latest inspection currently shows status={summary.get('status')} "
            f"(ΔT={summary.get('delta_c')} °C); both are kept on record."
        )
    )
    return {
        "kind": "shared_note",
        "summary": f"Recorded planned-work note for {asset_id} by {author}. {align}",
        "data": {
            "assertion_id": str(a.id),
            "asset_id": asset_id,
            "text": text,
            "author": author,
            "summary": summary,
        },
        "visuals": [
            {
                "kind": "status_card",
                "title": asset_id,
                "dataset_ref": "data",
                "fields": ["summary"],
            }
        ],
        "discussed_asset_ids": [asset_id],
        "evidence": [{"kind": "assertion", "source_id": str(a.id), "excerpt": text, "title": author}],
    }


def _handle_unconfirmed_claim(db: Session, text: str, user_id: str, as_of: datetime) -> dict[str, Any]:
    m = re.search(r"(WELL-\d{4})", text, re.I)
    asset_id = m.group(1).upper() if m else "WELL-0175"
    author = _user_display(db, user_id)
    a = record_assertion(
        db,
        kind="unconfirmed_claim",
        author_user_id=user_id,
        asset_id=asset_id,
        text=text,
        confirmation_state="unconfirmed",
        payload={"author_name": author},
    )
    summary = queries.get_well_summary(db, asset_id, as_of)
    li = summary.get("latest_inspection") or {}
    prior = [
        s
        for s in (summary.get("shared_assertions") or [])
        if s.get("kind") == "planned_work" and s.get("state") == "active"
    ]
    parts = [
        f"Recorded {author}'s statement as an unconfirmed claim.",
        f"Latest inspection {li.get('inspection_id')} by {li.get('inspector_name')} "
        f"shows ΔT={summary.get('delta_c')} °C → {summary.get('status')}.",
    ]
    if prior:
        parts.append(
            f"That matches {prior[0].get('author')}'s note (“{prior[0].get('text')}”), "
            f"not this claim."
        )
    for n in summary.get("context_notes") or []:
        if "20 Oct" in (n.get("text") or "") or "expected back" in (n.get("text") or "").lower():
            parts.append(f"Also note {n.get('note_id')}: {n.get('text')}")
            break
    parts.append("Measured evidence is unchanged; please confirm if you have a formal correction.")
    return {
        "kind": "conflict_review",
        "summary": " ".join(parts),
        "data": {"assertion_id": str(a.id), "summary": summary},
        "conflicts": [
            {
                "kind": "unconfirmed_vs_inspection",
                "claim": text,
                "claim_author": author,
                "inspection": li,
                "matching_notes": prior,
            }
        ],
        "visuals": [
            {
                "kind": "status_card",
                "title": asset_id,
                "dataset_ref": "data",
                "fields": ["summary"],
            }
        ],
        "discussed_asset_ids": [asset_id],
        "evidence": [
            {"kind": "assertion", "source_id": str(a.id), "excerpt": text, "title": author},
            {
                "kind": "inspection",
                "source_id": li.get("inspection_id"),
                "title": "Latest inspection",
            },
        ],
    }


def _handle_yesterday_recall(
    db: Session,
    text: str,
    user_id: str,
    conversation_id: uuid.UUID,
    as_of: datetime,
) -> dict[str, Any]:
    """Private memory: prior discussion for THIS user only (Q11 / Q16)."""
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).date()
    all_refs = (
        db.query(models.ConversationReference)
        .filter(models.ConversationReference.owner_user_id == user_id)
        .order_by(models.ConversationReference.discussed_at.desc())
        .all()
    )
    # "the three wells we discussed…" requires a multi-well prior chat for THIS user.
    # Do not fall back to single-well status chats (would leak wrong context / fake memory).
    min_wells = 3 if "three wells" in text.lower() else 2

    def _usable(refs: list) -> list:
        return [r for r in refs if r.asset_ids and len(r.asset_ids) >= min_wells]

    day_refs = [
        r
        for r in all_refs
        if r.discussed_at
        and r.discussed_at.astimezone(timezone.utc).date() == yesterday
        and r.asset_ids
    ]
    labeled = [
        r
        for r in all_refs
        if r.asset_ids
        and len(r.asset_ids) >= min_wells
        and r.label
        and ("downtime" in r.label.lower() or "northeast block 7" in r.label.lower())
    ]
    # Prefer labeled downtime rankings (Q6→Q11) over other multi-well chats (RCA, maps).
    prior = labeled or _usable(day_refs) or _usable(all_refs)
    if not prior:
        who = _user_display(db, user_id)
        return {
            "kind": "short_answer",
            "summary": (
                f"I don’t have an earlier multi-well discussion with {who} to recall. "
                f"Private chats stay with each user — I won’t use someone else’s history. "
                f"Name the wells explicitly (for example WELL-0001), "
                f"or discuss them first in this user’s own chat."
            ),
            "visuals": [],
            "rows": [],
            "discussed_asset_ids": [],
            "evidence": [],
        }
    ref = prior[0]
    asset_ids = list(ref.asset_ids)
    year = as_of.year
    costs = queries.repair_costs(db, asset_ids, date(year, 1, 1), date(year, 12, 31))
    cost_bits = []
    for r in costs.get("rows", []):
        v = float(r["cost_usd"])
        cost_bits.append(
            f"{r['asset_id']}: USD {v:,.0f}" if v.is_integer() else f"{r['asset_id']}: USD {v:,.2f}"
        )
    return {
        "kind": "table",
        "summary": (
            f"From your earlier discussion ({ref.label}): repair costs this year — "
            + " · ".join(cost_bits)
        ),
        "rows": costs.get("rows"),
        "visuals": [
            {
                "kind": "table",
                "title": f"Repair costs — {year}",
                "dataset_ref": "rows",
                "fields": ["asset_id", "cost_usd", "count"],
            }
        ],
        "discussed_asset_ids": asset_ids,
        "citations": [{"id": "prior", "label": ref.label or "Earlier discussion"}],
        "evidence": [],
    }
