"""Build readable evidence items from answer rows/citations when capabilities omit them."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.db import models

_ID_RE = re.compile(r"\b((?:INS|MNT|CTX|WELL|MOC)-\S+|\bLOT-\S+)\b", re.I)


def synthesize_evidence(
    *,
    rows: list[dict[str, Any]] | None,
    citations: list[dict[str, Any]] | None = None,
    db: Session | None = None,
    limit: int = 120,
) -> list[dict[str, Any]]:
    """Return evidence dicts suitable for EvidenceItem / API items."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(
        kind: str,
        *,
        source_id: str | None = None,
        title: str | None = None,
        excerpt: str | None = None,
        source_path: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        key = (kind, str(source_id or title or excerpt or "")[:120])
        if key in seen or not (source_id or title or excerpt):
            return
        seen.add(key)
        out.append(
            {
                "kind": kind,
                "source_id": source_id,
                "source_path": source_path,
                "locator": None,
                "title": title,
                "excerpt": excerpt,
                "meta": meta or {},
            }
        )

    # Citations first (SOP / letter authority)
    for c in citations or []:
        cid = str(c.get("id") or "")
        label = str(c.get("label") or cid)
        if not cid and not label:
            continue
        kind = "sop"
        low = (cid + " " + label).lower()
        if "letter" in low or "regulator" in low or "commission" in low:
            kind = "regulator"
        elif "recall" in low or "supplier" in low:
            kind = "manual"
        elif "inspection" in low:
            kind = "inspection"
        path = None
        excerpt = label
        if db is not None:
            doc = None
            if cid:
                doc = (
                    db.query(models.Document)
                    .filter(
                        (models.Document.doc_key == cid)
                        | (models.Document.doc_key.ilike(f"%{cid}%"))
                        | (models.Document.title.ilike(f"%{label[:40]}%"))
                    )
                    .first()
                )
            if doc is None and ("ops-" in low or "operations" in low or "sop" in low):
                doc = (
                    db.query(models.Document)
                    .filter(models.Document.doc_key.ilike("%operations-sop%"))
                    .first()
                )
            if doc is None and ("moc" in low or "bypass" in low):
                doc = (
                    db.query(models.Document)
                    .filter(models.Document.doc_key.ilike("%moc-%"))
                    .first()
                )
            if doc is None and ("regulator" in low or "letter" in low or "commission" in low):
                doc = (
                    db.query(models.Document)
                    .filter(models.Document.doc_key.ilike("%regulator-letter%"))
                    .first()
                )
            if doc:
                path = doc.path or doc.doc_key
                excerpt = (doc.body or label)[:500]
                add(
                    kind,
                    source_id=doc.doc_key,
                    title=doc.title or label,
                    excerpt=excerpt,
                    source_path=path,
                    meta={"from": "citation"},
                )
                continue
        add(kind, source_id=cid or None, title=label, excerpt=excerpt, meta={"from": "citation"})

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        aid = str(row.get("asset_id") or "well")

        note_id = row.get("note_id")
        note_quote = row.get("note_quote") or row.get("operator_note_evidence")
        if note_id or note_quote:
            add(
                "operator_note",
                source_id=str(note_id) if note_id else None,
                title=f"{aid} · operator note",
                excerpt=str(note_quote) if note_quote else None,
                meta={"asset_id": aid, "reported_at": row.get("reported_at")},
            )

        if row.get("latest_operator_note"):
            add(
                "operator_note",
                source_id=str(row.get("note_id") or "") or None,
                title=f"{aid} · latest operator note",
                excerpt=str(row.get("latest_operator_note")),
                meta={"asset_id": aid, "status_now": row.get("status_now")},
            )

        insp = row.get("inspection_id") or row.get("inspection")
        if insp:
            add(
                "inspection",
                source_id=str(insp).split()[0] if insp else None,
                title=f"{aid} · inspection",
                excerpt=str(insp) if not row.get("latest_inspection") else str(row.get("latest_inspection")),
                meta={"asset_id": aid, "volume_bbl": row.get("volume_bbl")},
            )

        if row.get("latest_inspection"):
            add(
                "inspection",
                source_id=str(row.get("inspection_id") or "") or None,
                title=f"{aid} · latest inspection",
                excerpt=str(row.get("latest_inspection")),
                meta={"asset_id": aid, "status_now": row.get("status_now")},
            )

        resp = row.get("response")
        if isinstance(resp, str) and resp.lower() != "none":
            m = _ID_RE.search(resp)
            sid = m.group(1).upper() if m else None
            kind = "maintenance" if sid and sid.startswith("MNT") else "inspection" if sid and sid.startswith("INS") else "record"
            add(
                kind,
                source_id=sid,
                title=f"{aid} · response",
                excerpt=resp,
                meta={
                    "asset_id": aid,
                    "hours_to_response": row.get("hours_to_response"),
                    "met": row.get("met"),
                    "deadline_hours": row.get("deadline_hours"),
                },
            )

        approval = row.get("approval")
        if approval and str(approval).lower() not in ("none", "n/a", ""):
            add(
                "sop",
                source_id=str(approval),
                title=f"{aid} · bypass approval",
                excerpt=(
                    f"Approval {approval}; valid until {row.get('approval_valid_until') or 'n/a'}; "
                    f"status {row.get('status')}; in {row.get('bypass_in')}, out {row.get('bypass_out')}"
                ),
                meta={"asset_id": aid},
            )
        elif row.get("bypass_in") or row.get("status"):
            add(
                "operator_note",
                source_id=None,
                title=f"{aid} · bypass interval",
                excerpt=(
                    f"Bypass in {row.get('bypass_in')}, out {row.get('bypass_out') or 'still in'}; "
                    f"status {row.get('status')}"
                ),
                meta={"asset_id": aid},
            )

        cleanup = row.get("cleanup_job")
        if cleanup:
            add(
                "maintenance",
                source_id=str(cleanup).split()[0],
                title=f"{aid} · cleanup job",
                excerpt=str(cleanup),
                meta={"asset_id": aid, "compliant": row.get("compliant")},
            )

        if row.get("lot") or row.get("provenance"):
            add(
                "record",
                source_id=str(row.get("lot") or aid),
                title=f"{aid} · recalled pump",
                excerpt=str(row.get("provenance") or row.get("lot")),
                meta={"asset_id": aid, "area_name": row.get("area_name")},
            )

        if row.get("last_repair") and not note_quote:
            add(
                "maintenance",
                source_id=None,
                title=f"{aid} · last repair",
                excerpt=str(row.get("last_repair")),
                meta={"asset_id": aid, "rank": row.get("rank")},
            )

        if row.get("reason") and row.get("share_pct") is not None:
            add(
                "record",
                source_id=None,
                title=f"{row.get('area_name') or 'Area'} · wait reason",
                excerpt=(
                    f"{row.get('reason')}: {row.get('share_pct')}% of extra days; "
                    f"typical extra {row.get('typical_extra_days')} days"
                ),
                meta={"area_name": row.get("area_name")},
            )

        if row.get("mean_delta_c") is not None and row.get("area_name"):
            add(
                "inspection",
                source_id=None,
                title=f"{row.get('area_name')} · temperature",
                excerpt=(
                    f"Mean wellhead−ambient ΔT {row.get('mean_delta_c')}°C "
                    f"(median {row.get('median_delta_c', '—')}°C, n={row.get('samples', '—')})"
                ),
                meta={
                    "area_name": row.get("area_name"),
                    "mean_delta_c": row.get("mean_delta_c"),
                    "samples": row.get("samples"),
                },
            )

        if len(out) >= limit:
            break

    return out[:limit]


def enrich_answer_evidence(answer: dict[str, Any], db: Session | None = None) -> dict[str, Any]:
    """If answer.evidence is empty, fill from rows + citations (mutates and returns answer)."""
    existing = answer.get("evidence") or []
    if existing:
        return answer
    if (answer.get("coverage") or {}).get("status") == "unsupported":
        return answer
    rows = answer.get("rows")
    if not isinstance(rows, list):
        rows = []
    synthesized = synthesize_evidence(
        rows=rows,
        citations=answer.get("citations") or [],
        db=db,
    )
    if synthesized:
        answer["evidence"] = synthesized
    return answer
