"""Operations SOP algorithms (OPS-1 gas, OPS-2 bypass, OPS-3 status precedence)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.effective import effective_inspection
from app.db import models
from app.domain.production import ProductionStatus


GAS_PAT = re.compile(
    r"gas\s*(smell|odor|odour)|strong\s+gas|rotten[\s-]?egg|h2s\s*(monitor|alarm)|smelled\s+gas",
    re.I,
)
BYPASS_IN = re.compile(r"bypass\s+(put\s+)?in|temporary\s+bypass\s+(installed|in\s+place)|put\s+.*bypass", re.I)
BYPASS_OUT = re.compile(r"bypass\s+(taken\s+)?out|removed\s+.*bypass|bypass\s+removed", re.I)
SHUT_IN = re.compile(r"\bshut[\s-]?in\b|\bshut\s+in\b", re.I)
RESTART = re.compile(r"\brestarted\b|\bback\s+online\b|\breturned\s+to\s+(production|service)\b", re.I)


def _gas_deadline_hours(noted_at: datetime) -> int:
    # OPS-1: 24h before 2027-01-01, 12h from 2027-01-01
    cutoff = datetime(2027, 1, 1, tzinfo=timezone.utc)
    return 12 if noted_at >= cutoff else 24


def gas_odor_compliance(
    db: Session,
    *,
    since: datetime,
    as_of: datetime,
) -> dict[str, Any]:
    notes = (
        db.query(models.SourceNote)
        .filter(
            models.SourceNote.note_type == "operator_note",
            models.SourceNote.created_at >= since,
            models.SourceNote.created_at <= as_of,
        )
        .order_by(models.SourceNote.created_at.asc())
        .all()
    )
    rows: list[dict[str, Any]] = []
    for note in notes:
        if not GAS_PAT.search(note.text or ""):
            continue
        well = db.get(models.Well, note.asset_id)
        area = db.get(models.Area, well.area_id) if well else None
        deadline_h = _gas_deadline_hours(note.created_at)
        deadline_at = note.created_at + timedelta(hours=deadline_h)

        # Next response: maintenance started after note, or manual inspection after note
        mnt = (
            db.query(models.Maintenance)
            .filter(
                models.Maintenance.asset_id == note.asset_id,
                models.Maintenance.started_at > note.created_at,
                models.Maintenance.started_at <= as_of,
            )
            .order_by(models.Maintenance.started_at.asc())
            .first()
        )
        insp = (
            db.query(models.Inspection)
            .filter(
                models.Inspection.asset_id == note.asset_id,
                models.Inspection.inspected_at > note.created_at,
                models.Inspection.inspected_at <= as_of,
                models.Inspection.method == "manual",
            )
            .order_by(models.Inspection.inspected_at.asc())
            .first()
        )
        response_id = None
        response_at = None
        if mnt and insp:
            if mnt.started_at <= insp.inspected_at:
                response_id, response_at = mnt.maintenance_id, mnt.started_at
            else:
                response_id, response_at = insp.inspection_id, insp.inspected_at
        elif mnt:
            response_id, response_at = mnt.maintenance_id, mnt.started_at
        elif insp:
            response_id, response_at = insp.inspection_id, insp.inspected_at

        hours = None
        met = "Missed"
        if response_at is not None:
            hours = round((response_at - note.created_at).total_seconds() / 3600.0, 2)
            met = "Met" if response_at <= deadline_at else "Missed"
        rows.append(
            {
                "asset_id": note.asset_id,
                "area_name": area.name if area else None,
                "reported_at": note.created_at.isoformat(),
                "response": f"{response_id} @ {response_at.isoformat()}" if response_id else "none",
                "hours_to_response": hours,
                "deadline_hours": deadline_h,
                "deadline_at": deadline_at.isoformat(),
                "met": met,
                "note_id": note.note_id,
                "note_quote": (note.text or "")[:240],
            }
        )
    return {
        "count": len(rows),
        "rows": rows,
        "since": since.isoformat(),
        "as_of": as_of.isoformat(),
    }


def _parse_moc_docs(db: Session) -> list[dict[str, Any]]:
    docs = (
        db.query(models.Document)
        .filter(models.Document.doc_key.like("fleet/sops/moc-%"))
        .all()
    )
    out: list[dict[str, Any]] = []
    for doc in docs:
        wells = [m.group(1).upper() for m in re.finditer(r"\b(WELL-\d{4})\b", doc.body)]
        eff = None
        exp = None
        m_eff = re.search(r"Effective from\s+(\d{1,2}\s+\w+\s+20\d{2})", doc.body, re.I)
        m_exp = re.search(r"expires on\s+(\d{1,2}\s+\w+\s+20\d{2})", doc.body, re.I)
        for label, m in (("eff", m_eff), ("exp", m_exp)):
            if not m:
                continue
            try:
                from datetime import datetime as dt

                d = dt.strptime(m.group(1), "%d %b %Y").date()
            except ValueError:
                try:
                    d = dt.strptime(m.group(1), "%d %B %Y").date()
                except ValueError:
                    d = None
            if label == "eff":
                eff = d
            else:
                exp = d
        memo_id = doc.title or doc.doc_key.split("/")[-1].replace(".md", "")
        out.append(
            {
                "memo_id": memo_id.upper() if memo_id else doc.doc_key,
                "wells": wells,
                "effective": eff,
                "expires": exp,
                "doc_key": doc.doc_key,
            }
        )
    return out


def temporary_bypasses(db: Session, *, as_of: datetime) -> dict[str, Any]:
    mocs = _parse_moc_docs(db)
    notes = (
        db.query(models.SourceNote)
        .filter(models.SourceNote.note_type == "operator_note")
        .order_by(models.SourceNote.created_at.asc())
        .all()
    )
    # Track bypass intervals per well
    events: dict[str, list[tuple[str, datetime, str]]] = {}
    for note in notes:
        text = note.text or ""
        if BYPASS_OUT.search(text):
            events.setdefault(note.asset_id, []).append(("out", note.created_at, note.note_id))
        elif BYPASS_IN.search(text) or ("bypass" in text.lower() and "out" not in text.lower() and "remov" not in text.lower()):
            if "bypass" in text.lower():
                events.setdefault(note.asset_id, []).append(("in", note.created_at, note.note_id))

    rows: list[dict[str, Any]] = []
    today = as_of.date()

    def moc_for(asset_id: str, on: date) -> dict[str, Any] | None:
        best = None
        for moc in mocs:
            if asset_id not in moc["wells"]:
                continue
            if moc["effective"] and on < moc["effective"]:
                continue
            # later expiry wins if extending
            if best is None or (moc["expires"] or date.max) >= (best["expires"] or date.min):
                best = moc
        return best

    for asset_id, evs in events.items():
        open_in: datetime | None = None
        open_note = None
        intervals: list[tuple[datetime, datetime | None, str, str | None]] = []
        for kind, at, nid in evs:
            if kind == "in":
                open_in = at
                open_note = nid
            elif kind == "out" and open_in is not None:
                intervals.append((open_in, at, open_note or "", nid))
                open_in = None
                open_note = None
        if open_in is not None:
            intervals.append((open_in, None, open_note or "", None))

        well = db.get(models.Well, asset_id)
        area = db.get(models.Area, well.area_id) if well else None
        for start, end, _nid_in, _nid_out in intervals:
            end_date = end.date() if end else None
            still_in = end is None or end > as_of
            # Status against approval for the period the bypass was in
            check_day = today if still_in else (end_date or today)
            moc = moc_for(asset_id, start.date())
            if moc is None:
                status = "Not approved"
                approval = "none"
                valid_until = None
            else:
                approval = moc["memo_id"]
                valid_until = moc["expires"].isoformat() if moc["expires"] else None
                if moc["expires"] and check_day > moc["expires"]:
                    status = "Expired"
                elif still_in and moc["expires"] and today > moc["expires"]:
                    status = "Expired"
                else:
                    status = "Allowed"
            # Also flag historical intervals that overran
            if end_date and moc and moc["expires"] and end_date > moc["expires"]:
                status = "Expired"
            rows.append(
                {
                    "asset_id": asset_id,
                    "area_name": area.name if area else None,
                    "bypass_in": start.date().isoformat(),
                    "bypass_out": end_date.isoformat() if end_date else "still in",
                    "approval": approval,
                    "approval_valid_until": valid_until,
                    "status": status,
                    "active_now": still_in,
                }
            )

    # Sort: active first, then by well
    rows.sort(key=lambda r: (not r["active_now"], r["area_name"] or "", r["asset_id"]))
    return {"count": len(rows), "rows": rows, "as_of": as_of.isoformat()}


def status_disagreements(db: Session, *, as_of: datetime) -> dict[str, Any]:
    """OPS-3: wells where latest inspection and latest shut-in/restart note disagree."""
    wells = db.query(models.Well).all()
    rows: list[dict[str, Any]] = []
    for well in wells:
        insp = (
            db.query(models.Inspection)
            .filter(
                models.Inspection.asset_id == well.asset_id,
                models.Inspection.inspected_at <= as_of,
            )
            .order_by(models.Inspection.inspected_at.desc())
            .first()
        )
        if not insp:
            continue
        eff = effective_inspection(db, insp, well.well_type)
        insp_status = eff.classification.status.value
        delta_c = None
        if eff.wellhead_temp_c is not None and eff.ambient_temp_c is not None:
            delta_c = float(eff.wellhead_temp_c - eff.ambient_temp_c)

        notes = (
            db.query(models.SourceNote)
            .filter(
                models.SourceNote.asset_id == well.asset_id,
                models.SourceNote.note_type == "operator_note",
                models.SourceNote.created_at <= as_of,
            )
            .order_by(models.SourceNote.created_at.desc())
            .all()
        )
        status_note = None
        for n in notes:
            if SHUT_IN.search(n.text or "") or RESTART.search(n.text or ""):
                status_note = n
                break
        if status_note is None:
            continue
        note_says_shut = bool(SHUT_IN.search(status_note.text or ""))
        note_says_restart = bool(RESTART.search(status_note.text or "")) and not note_says_shut
        note_after_insp = status_note.created_at > insp.inspected_at

        # Disagreement: note and inspection imply different producing states
        insp_producing = insp_status == ProductionStatus.PRODUCING.value
        disagree = False
        if note_says_shut and insp_producing:
            disagree = True
        if note_says_restart and not insp_producing:
            disagree = True
        if note_after_insp and note_says_shut and insp_producing:
            disagree = True
        if not disagree:
            # Also surface when note after insp flips status vs insp
            if note_after_insp and (note_says_shut or note_says_restart):
                disagree = True
        if not disagree:
            continue

        # Real status now per OPS-3
        unconfirmed = False
        if note_after_insp and note_says_shut:
            real = "Not producing oil"
            why = "Operator shut-in note is more recent than the latest inspection (OPS-3)."
        elif note_after_insp and note_says_restart:
            real = "Producing oil"
            unconfirmed = True
            why = "Operator restart note is more recent than the latest inspection — producing (unconfirmed) until an inspection confirms (OPS-3)."
        else:
            # inspection wins when note is older
            real = "Producing oil" if insp_producing else "Not producing oil"
            why = "Latest inspection governs because it is more recent than the operator status note."

        area = db.get(models.Area, well.area_id)
        insp_label = "producing" if insp_producing else "not producing"
        rows.append(
            {
                "asset_id": well.asset_id,
                "area_name": area.name if area else None,
                "inspection_id": insp.inspection_id,
                "note_id": status_note.note_id,
                "latest_inspection": (
                    f"{insp.inspection_id}, {insp.inspected_at.date().isoformat()}, "
                    f"{insp_label} (ΔT={delta_c})"
                ),
                "latest_operator_note": (
                    f"{status_note.created_at.isoformat()}, {(status_note.text or '')[:180]}"
                ),
                "status_now": f"{real}" + (" (unconfirmed)" if unconfirmed else "") + f" — {why}",
                "_evidence": [
                    {
                        "kind": "inspection",
                        "source_id": insp.inspection_id,
                        "source_path": insp.source_path,
                        "title": f"{well.asset_id} · latest inspection",
                        "excerpt": (
                            f"{insp.inspected_at.isoformat()} · method={insp.method} · "
                            f"wellhead={eff.wellhead_temp_c}°C ambient={eff.ambient_temp_c}°C · "
                            f"ΔT={delta_c} → {insp_label} (threshold for {well.well_type})"
                        ),
                        "meta": {
                            "asset_id": well.asset_id,
                            "role": "latest_inspection",
                            "status": insp_label,
                        },
                    },
                    {
                        "kind": "operator_note",
                        "source_id": status_note.note_id,
                        "source_path": status_note.source_path,
                        "title": f"{well.asset_id} · operator status note",
                        "excerpt": (
                            f"{status_note.created_at.isoformat()} · "
                            f"{'shut-in' if note_says_shut else 'restart' if note_says_restart else 'status'} · "
                            f"{status_note.text}"
                        ),
                        "meta": {
                            "asset_id": well.asset_id,
                            "role": "operator_note",
                            "note_type": status_note.note_type,
                        },
                    },
                ],
            }
        )
    rows.sort(key=lambda r: (r["area_name"] or "", r["asset_id"]))
    evidence: list[dict[str, Any]] = []
    for r in rows:
        evidence.extend(r.pop("_evidence", []))
    # SOP authority once at the top
    sop = (
        db.query(models.Document)
        .filter(models.Document.doc_key.like("%operations-sop%"))
        .first()
    )
    if sop:
        evidence.insert(
            0,
            {
                "kind": "sop",
                "source_id": sop.doc_key,
                "source_path": sop.path,
                "title": "OPS-3 Status evidence precedence",
                "excerpt": (
                    "A well's current status comes from the most recent of: its latest "
                    "inspection reading (after corrections), or its latest operator note "
                    "saying the well was shut in or restarted. Restart after inspection = "
                    "producing (unconfirmed) until an inspection confirms."
                ),
                "meta": {"protocol": "OPS-3"},
            },
        )
    return {"count": len(rows), "rows": rows, "evidence": evidence}
