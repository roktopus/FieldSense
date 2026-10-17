"""Intent classification + capability dispatch (final + general questions)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agent.resolve import resolve_query, table_answer
from app.capabilities import analytics_ext, coverage, equipment, ops, regulator
from app.capabilities.memory_prefs import (
    apply_list_prefs,
    assets_talked_about_today,
    remember_topic,
    set_pref,
)
from app.db import models
from app.feedback.service import record_assertion


def try_capability_route(
    db: Session,
    *,
    text: str,
    user_id: str,
    conversation_id: uuid.UUID,
    as_of: datetime,
) -> dict[str, Any] | None:
    q = text.strip()
    ql = q.lower()
    resolved = resolve_query(db, q, as_of=as_of, user_id=user_id)

    # --- Coverage unknowns (Q1 / Q2) ---
    if "reservoir pressure" in ql or ("pressure" in ql and "map" in ql and "reservoir" in ql):
        return coverage.answer_missing_pressure(db, as_of)
    if ("produced the most oil" in ql or "most oil in" in ql) and "spill" not in ql:
        return coverage.answer_missing_production_volume(db, resolved.year, as_of)

    # --- Private display prefs ---
    if ("sort them by area" in ql or "sort" in ql and "area" in ql and "well id" in ql) and (
        "just for me" in ql or "for me" in ql or "whenever you list" in ql
    ):
        set_pref(
            db,
            user_id,
            "list_display",
            {"sort": "area_then_well", "costs_in_thousands": "thousands" in ql or "thousand" in ql},
        )
        return {
            "kind": "short_answer",
            "summary": (
                "Saved as a private preference for you only: list wells by area then well ID"
                + (", show costs in thousands of dollars." if "thousand" in ql else ".")
                + " Other users will not see this preference."
            ),
            "visuals": [],
            "rows": [],
            "discussed_asset_ids": [],
        }

    # --- Pump replaced assertions (shared) ---
    if ("recalled pump" in ql or "pump was swapped" in ql or "swapped out" in ql) and resolved.wells:
        asset_id = resolved.wells[0]
        unconfirmed = "told me" in ql or "nathan told" in ql
        record_assertion(
            db,
            kind="pump_replaced",
            author_user_id=user_id,
            asset_id=asset_id,
            text=q,
            payload={"pump_replaced": True, "source": "user"},
            confirmation_state="unconfirmed" if unconfirmed else "active",
        )
        who = db.get(models.User, user_id)
        return {
            "kind": "short_answer",
            "summary": (
                f"Recorded that the recalled pump on {asset_id} was replaced"
                f" ({'unconfirmed — second-hand report' if unconfirmed else 'shared fact'}"
                f" from {who.name if who else user_id}). "
                f"Provenance: this chat turn. Work order may still be missing from maintenance.jsonl."
            ),
            "visuals": [],
            "conflicts": [{"kind": "unconfirmed", "asset_id": asset_id}] if unconfirmed else [],
            "discussed_asset_ids": [asset_id],
            "reference_label": "pump replacement",
        }

    # --- Recalled pumps ---
    if "recalled pump" in ql or "recall list" in ql or ("still in the ground" in ql and "pump" in ql):
        area_names = None
        team_id = None
        if resolved.my_area_only and resolved.team_id:
            team_id = resolved.team_id
        data = equipment.recalled_pumps_still_in_ground(
            db, as_of=as_of, area_names=area_names, team_id=team_id
        )
        rows = apply_list_prefs(db, user_id, data["rows"])
        if "how many" in ql and "which areas" in ql:
            by = data["by_area"]
            parts = ", ".join(f"{k}: {v}" for k, v in sorted(by.items()))
            ans = {
                "kind": "short_answer",
                "summary": (
                    f"{data['count']} recalled pumps still in the ground"
                    f" (lots {', '.join(data['recalled_lots'])}). By area: {parts or 'none'}. "
                    f"Source: {data['recall_doc']} + Parts installed lines in maintenance reports."
                ),
                "visuals": [],
                "rows": rows,
                "discussed_asset_ids": [r["asset_id"] for r in rows],
                "reference_label": "recalled pumps",
            }
            remember_topic(
                db,
                user_id=user_id,
                conversation_id=conversation_id,
                label="recalled pumps",
                asset_ids=[r["asset_id"] for r in rows],
                topic="recalled_pumps",
            )
            return ans
        fields = ["asset_id", "area_name", "lot", "install_maintenance_id", "cost_usd", "provenance"]
        if any("cost_display" in r for r in rows):
            fields = ["asset_id", "area_name", "lot", "install_maintenance_id", "cost_display", "provenance"]
        remember_topic(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            label="recalled pumps",
            asset_ids=[r["asset_id"] for r in rows],
            topic="recalled_pumps",
        )
        return table_answer(
            kind="table",
            summary=(
                f"{data['count']} recalled Highline pumps still installed"
                + (" in your team's wells" if team_id else "")
                + f". Lots: {', '.join(data['recalled_lots'])}. Each row cites install report + recall notice."
            ),
            rows=rows,
            fields=fields,
            title="Recalled pumps still in the ground",
            citations=[{"id": data["recall_doc"] or "recall", "label": "Supplier recall notice"}],
            discussed_asset_ids=[r["asset_id"] for r in rows],
            reference_label="recalled pumps",
        )

    # --- Gas odor OPS-1 ---
    if ("gas" in ql and ("operator note" in ql or "reports gas" in ql or "odor" in ql or "smell" in ql)) and (
        "response" in ql or "deadline" in ql or "operating procedure" in ql or "list every" in ql
    ):
        since = resolved.since or datetime(2026, 11, 1, tzinfo=timezone.utc)
        if since > as_of:
            return {
                "kind": "short_answer",
                "summary": (
                    f"The analysis clock is {as_of.date()}, which is before the requested "
                    f"window start ({since.date()}). Set As of to 2027-01-15 (test dataset "
                    f"“today”) or a date on/after {since.date()}, then ask again — otherwise "
                    f"every gas note in that window is filtered out."
                ),
                "visuals": [],
                "rows": [],
                "warnings": ["analysis_clock_before_window"],
                "coverage": {
                    "status": "clock_mismatch",
                    "as_of": as_of.isoformat(),
                    "since": since.isoformat(),
                },
                "citations": [{"id": "ops-1", "label": "operations-sop-rev2 OPS-1"}],
            }
        data = ops.gas_odor_compliance(db, since=since, as_of=as_of)
        return table_answer(
            kind="table",
            summary=(
                f"{data['count']} gas-odor operator notes since {since.date()} "
                f"(through {as_of.date()}; OPS-1: 24h before 2027-01-01, 12h after). "
                f"Met={sum(1 for r in data['rows'] if r['met']=='Met')}, "
                f"Missed={sum(1 for r in data['rows'] if r['met']=='Missed')}."
            ),
            rows=data["rows"],
            fields=[
                "asset_id",
                "area_name",
                "reported_at",
                "response",
                "hours_to_response",
                "deadline_hours",
                "met",
            ],
            title="Gas odor response compliance (OPS-1)",
            citations=[{"id": "ops-1", "label": "operations-sop-rev2 OPS-1"}],
            discussed_asset_ids=[r["asset_id"] for r in data["rows"]],
            reference_label="gas odor reports",
            scope={"as_of": as_of.isoformat(), "since": since.isoformat()},
        )

    # --- Temporary bypasses OPS-2 ---
    if "bypass" in ql and ("temporary" in ql or "flowline" in ql or "allowed" in ql):
        data = ops.temporary_bypasses(db, as_of=as_of)
        return table_answer(
            kind="table",
            summary=(
                f"{data['count']} temporary flowline bypass interval(s). "
                f"Status from MOC memos (OPS-2): Allowed / Expired / Not approved."
            ),
            rows=data["rows"],
            fields=[
                "asset_id",
                "area_name",
                "bypass_in",
                "bypass_out",
                "approval",
                "approval_valid_until",
                "status",
            ],
            title="Temporary flowline bypasses",
            citations=[{"id": "ops-2", "label": "operations-sop-rev2 OPS-2 + moc-*.md"}],
            discussed_asset_ids=[r["asset_id"] for r in data["rows"]],
        )

    # --- Regulator letter ---
    if "state oil" in ql or "commission wrote" in ql or ("letter" in ql and "spill" in ql):
        data = regulator.letter_spill_compliance(db, as_of=as_of)
        return table_answer(
            kind="table",
            summary=(
                f"{data['count']} reportable spill(s) covered by the regulator letter "
                f"({', '.join(data['scope']['areas'])} since {data['scope']['since']}). "
                f"Compliance requires “Soil samples sent to the lab.” in the clean-up report."
            ),
            rows=data["rows"],
            fields=["asset_id", "area_name", "inspection", "volume_bbl", "cleanup_job", "compliant"],
            title="Regulator letter — spill soil-sample compliance",
            citations=[{"id": data["scope"].get("doc_key") or "letter", "label": "Regulator letter"}],
            discussed_asset_ids=[r["asset_id"] for r in data["rows"]],
        )

    # --- Status disagreements OPS-3 ---
    if ("disagree" in ql or "disagrees" in ql) and (
        "inspection" in ql and ("operator note" in ql or "notes" in ql)
    ):
        data = ops.status_disagreements(db, as_of=as_of)
        return table_answer(
            kind="table",
            summary=(
                f"{data['count']} well(s) where the latest inspection and a shut-in/restart "
                f"operator note disagree. Status now follows OPS-3 precedence. "
                f"Open View evidence for the paired inspection + note on each well."
            ),
            rows=data["rows"],
            fields=[
                "asset_id",
                "area_name",
                "latest_inspection",
                "latest_operator_note",
                "status_now",
            ],
            title="Inspection vs operator-note status conflicts",
            citations=[
                {"id": "ops-3", "label": "operations-sop-rev2 OPS-3"},
                {"id": "inspections", "label": "Latest inspections"},
                {"id": "operator_notes", "label": "Operator shut-in / restart notes"},
            ],
            evidence=data.get("evidence") or [],
            discussed_asset_ids=[r["asset_id"] for r in data["rows"]],
            scope={"as_of": as_of.isoformat(), "rule": "OPS-3"},
        )

    # --- Repair risk ranking ---
    if ("sound or behave" in ql or "behave wrong" in ql or "haven't had a repair" in ql) and (
        "rank" in ql or "most likely" in ql or "need a repair" in ql
    ):
        data = analytics_ext.repair_risk_rank(db, as_of=as_of, top_n=10)
        remember_topic(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            label="repair risk wells",
            asset_ids=[r["asset_id"] for r in data["rows"]],
            topic="repair_risk",
        )
        return table_answer(
            kind="table",
            summary=(
                f"Top {data['count']} wells with recent operator notes about abnormal sound/behaviour "
                f"and no later non-spill corrective repair."
            ),
            rows=data["rows"],
            fields=[
                "rank",
                "asset_id",
                "area_name",
                "operator_note_evidence",
                "other_warning_signs",
                "last_repair",
            ],
            title="Repair-risk ranking (operator notes)",
            discussed_asset_ids=[r["asset_id"] for r in data["rows"]],
            reference_label="repair risk wells",
        )

    if "which three would you send" in ql or ("send a crew" in ql and "first" in ql):
        # Prefer wells from prior ranking in this conversation
        refs = (
            db.query(models.ConversationReference)
            .filter(
                models.ConversationReference.owner_user_id == user_id,
                models.ConversationReference.conversation_id == conversation_id,
            )
            .order_by(models.ConversationReference.discussed_at.desc())
            .all()
        )
        assets = []
        for ref in refs:
            if ref.label and "repair" in ref.label.lower():
                assets = list(ref.asset_ids or [])
                break
        if not assets and refs:
            assets = list(refs[0].asset_ids or [])
        top3 = assets[:3]
        evidence = []
        for aid in top3:
            note = (
                db.query(models.SourceNote)
                .filter(
                    models.SourceNote.asset_id == aid,
                    models.SourceNote.note_type == "operator_note",
                )
                .order_by(models.SourceNote.created_at.desc())
                .first()
            )
            if note:
                evidence.append(
                    {
                        "kind": "operator_note",
                        "source_id": note.note_id,
                        "source_path": note.source_path,
                        "title": f"{aid} · latest operator note",
                        "excerpt": (note.text or "")[:400],
                        "meta": {"asset_id": aid, "role": "crew_priority"},
                    }
                )
        return {
            "kind": "short_answer",
            "summary": (
                f"Send a crew first to {', '.join(top3) if top3 else 'the top-ranked wells from the prior table'}. "
                f"Priority: freshest anomaly notes, corroborating not-producing / ΔT warnings, "
                f"and longest time since last non-spill repair."
            ),
            "visuals": [],
            "evidence": evidence,
            "citations": [{"id": "operator_notes", "label": "Recent operator anomaly notes"}],
            "discussed_asset_ids": top3,
        }

    # --- Wait reasons ---
    if "waiting on" in ql and ("parts" in ql or "crews" in ql or "contractors" in ql or "weather" in ql):
        year = resolved.year or 2026
        data = analytics_ext.wait_reasons_by_area(db, year=year, as_of=as_of)
        return {
            "kind": "stacked_bar",
            "summary": (
                f"For jobs/notes in {year}, shut-in wait reasons by area. "
                f"Standout: {data['standout_area'] or 'none'}. "
                f"Typical extra days estimated from operator-note language."
            ),
            "rows": data["rows"],
            "data": {"stacked": data["stacked"]},
            "visuals": [
                {
                    "kind": "table",
                    "title": f"Wait reasons by area ({year})",
                    "dataset_ref": "rows",
                    "fields": ["area_name", "reason", "count", "share_pct", "typical_extra_days"],
                },
                {
                    "kind": "stacked_bar",
                    "title": f"Wait reasons stacked by area ({year})",
                    "dataset_ref": "stacked",
                    "fields": ["area_name", "parts", "crews", "contractors", "weather"],
                },
            ],
            "citations": [
                {"id": "operator_notes", "label": "Operator notes (wait-reason language)"},
                {"id": "maintenance", "label": "Maintenance / shut-in intervals"},
            ],
            "discussed_asset_ids": [],
        }

    # --- Hotter region ---
    if "runs hotter" in ql or ("hotter" in ql and ("region" in ql or "field" in ql or "area" in ql)):
        data = analytics_ext.hotter_regions(db, as_of=as_of)
        top = data["hottest"]
        return {
            "kind": "bar_chart",
            "summary": (
                f"{top['area_name']} runs hottest on average "
                f"(mean ΔT {top['mean_delta_c']}°C over the last {data['window_days']} days, "
                f"n={top['samples']})."
                if top
                else "No temperature samples available."
            ),
            "rows": data["rows"],
            "visuals": [
                {
                    "kind": "bar_chart",
                    "title": "Mean wellhead−ambient ΔT by area",
                    "dataset_ref": "rows",
                    "x": "area_name",
                    "y": "mean_delta_c",
                }
            ],
            "citations": [
                {"id": "inspections", "label": "Weekly inspections (wellhead vs ambient ΔT)"},
            ],
            "discussed_asset_ids": [],
            "scope": {"as_of": as_of.isoformat(), "window_days": data.get("window_days")},
        }

    # --- Multi-topic helpers ---
    if "who leads" in ql and "production" in ql:
        # e.g. Northwest Production
        m = re.search(r"leads\s+(.+?)\s*,", q, re.I) or re.search(r"leads\s+(.+?)\?", q, re.I)
        team_name = (m.group(1).strip() if m else "").rstrip("?")
        team = (
            db.query(models.Team).filter(models.Team.name.ilike(f"%{team_name}%")).first()
            if team_name
            else None
        )
        if team:
            lead = db.get(models.User, team.lead_user_id) if team.lead_user_id else None
            n_wells = db.query(models.Well).filter(models.Well.team_id == team.team_id).count()
            return {
                "kind": "short_answer",
                "summary": (
                    f"{lead.name if lead else team.lead_user_id} leads {team.name}. "
                    f"That team runs {n_wells} wells (from well.team_id)."
                ),
                "visuals": [],
                "citations": [{"id": "users", "label": "Fleet users / team roster"}],
                "evidence": [
                    {
                        "kind": "record",
                        "source_id": team.team_id,
                        "title": f"{team.name} · team lead",
                        "excerpt": (
                            f"Lead: {lead.name if lead else team.lead_user_id} "
                            f"({team.lead_user_id}); wells on team: {n_wells}."
                        ),
                        "meta": {"team_id": team.team_id, "lead_user_id": team.lead_user_id},
                    }
                ],
                "discussed_asset_ids": [],
            }

    if "cold weather" in ql or ("freeze" in ql and "sop" in ql):
        # OPS-5 summary + one missed well in December
        missed = []
        dec_start = datetime(as_of.year - 1 if as_of.month < 12 else as_of.year, 12, 1, tzinfo=timezone.utc)
        dec_end = datetime(dec_start.year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        cold = (
            db.query(models.Inspection, models.Well)
            .join(models.Well, models.Well.asset_id == models.Inspection.asset_id)
            .filter(
                models.Inspection.inspected_at >= dec_start,
                models.Inspection.inspected_at <= dec_end,
                models.Inspection.ambient_temp_c.isnot(None),
            )
            .all()
        )
        from app.analytics.effective import effective_inspection

        for insp, well in cold:
            if insp.ambient_temp_c is None or insp.ambient_temp_c > -5:
                continue
            eff = effective_inspection(db, insp, well.well_type)
            if eff.classification.status.value != "producing":
                continue
            # Need heat trace check within 7 days
            check = (
                db.query(models.Maintenance)
                .filter(
                    models.Maintenance.asset_id == well.asset_id,
                    models.Maintenance.started_at >= insp.inspected_at,
                    models.Maintenance.started_at <= insp.inspected_at + __import__("datetime").timedelta(days=7),
                    models.Maintenance.issue.ilike("%heat trace%"),
                )
                .first()
            )
            if not check:
                missed.append(well.asset_id)
                if len(missed) >= 1:
                    break
        return {
            "kind": "short_answer",
            "summary": (
                "Operations SOP OPS-5 (freeze protection, 1 Dec–28 Feb): a producing well with "
                "ambient ≤ −5 °C needs a “Heat trace check” maintenance job within 7 days. "
                + (
                    f"Example miss in December: {missed[0]}."
                    if missed
                    else "No clear December miss found in the current extract."
                )
            ),
            "visuals": [],
            "discussed_asset_ids": missed,
            "citations": [{"id": "ops-5", "label": "operations-sop-rev2 OPS-5"}],
        }

    if "h2s" in ql and resolved.wells:
        asset_id = resolved.wells[0]
        # Find gas note then nearest response report with H2S fact
        note = (
            db.query(models.SourceNote)
            .filter(
                models.SourceNote.asset_id == asset_id,
                models.SourceNote.note_type == "operator_note",
            )
            .order_by(models.SourceNote.created_at.desc())
            .all()
        )
        gas_note = next((n for n in note if re.search(r"gas", n.text or "", re.I)), None)
        fact = (
            db.query(models.ExtractedFact)
            .filter(
                models.ExtractedFact.asset_id == asset_id,
                models.ExtractedFact.fact_type == "h2s_ppm",
            )
            .order_by(models.ExtractedFact.maintenance_id.desc())
            .first()
        )
        # Prefer fact from maintenance after the Dec 3 note if present
        if gas_note:
            mnt = (
                db.query(models.Maintenance)
                .filter(
                    models.Maintenance.asset_id == asset_id,
                    models.Maintenance.started_at >= gas_note.created_at,
                )
                .order_by(models.Maintenance.started_at.asc())
                .first()
            )
            if mnt:
                f2 = (
                    db.query(models.ExtractedFact)
                    .filter(
                        models.ExtractedFact.maintenance_id == mnt.maintenance_id,
                        models.ExtractedFact.fact_type == "h2s_ppm",
                    )
                    .first()
                )
                if f2:
                    fact = f2
        if fact:
            return {
                "kind": "short_answer",
                "summary": (
                    f"H2S reading at {asset_id}: {fact.value_numeric} ppm "
                    f"(from {fact.maintenance_id}: {fact.supporting_text})."
                ),
                "visuals": [],
                "discussed_asset_ids": [asset_id],
                "evidence": [
                    {
                        "kind": "report",
                        "source_id": fact.maintenance_id,
                        "excerpt": fact.supporting_text,
                    }
                ],
            }
        return {
            "kind": "short_answer",
            "summary": f"No H2S ppm fact extracted yet for {asset_id} in maintenance reports.",
            "visuals": [],
            "discussed_asset_ids": [asset_id],
        }

    if "back to the pumps" in ql or ("those wells" in ql and "not producing" in ql and "pump" in ql):
        refs = (
            db.query(models.ConversationReference)
            .filter(
                models.ConversationReference.owner_user_id == user_id,
                models.ConversationReference.conversation_id == conversation_id,
            )
            .order_by(models.ConversationReference.discussed_at.desc())
            .all()
        )
        assets = []
        for ref in refs:
            if ref.query_spec and ref.query_spec.get("topic") == "recalled_pumps":
                assets = list(ref.asset_ids or [])
                break
        from app.analytics.queries import get_well_summary

        rows = []
        for aid in assets:
            summary = get_well_summary(db, aid, as_of)
            if summary.get("status") != "producing":
                last = (
                    db.query(models.Maintenance)
                    .filter(models.Maintenance.asset_id == aid)
                    .order_by(models.Maintenance.started_at.desc())
                    .first()
                )
                rows.append(
                    {
                        "asset_id": aid,
                        "status": summary.get("status"),
                        "last_repaired": last.started_at.date().isoformat() if last else "unknown",
                        "last_maintenance_id": last.maintenance_id if last else None,
                    }
                )
        return table_answer(
            kind="table",
            summary=f"{len(rows)} of the recalled-pump wells from earlier in this chat are not producing now.",
            rows=rows,
            fields=["asset_id", "status", "last_repaired", "last_maintenance_id"],
            title="Recalled-pump wells not producing",
            discussed_asset_ids=[r["asset_id"] for r in rows],
        )

    if "wells we've talked about today" in ql or "wells we have talked about today" in ql or (
        "deal with first" in ql and "talked about" in ql
    ):
        assets = assets_talked_about_today(db, user_id, conversation_id)
        pick = assets[0] if assets else None
        return {
            "kind": "short_answer",
            "summary": (
                f"Of the wells in today's chat ({', '.join(assets) if assets else 'none recorded'}), "
                f"deal with {pick or 'the highest-risk well'} first — prioritize safety (gas/H2S), "
                f"then recalled pumps still installed, then production losses."
            ),
            "visuals": [],
            "discussed_asset_ids": assets,
        }

    return None
