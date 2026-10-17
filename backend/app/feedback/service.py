from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db import models


def preview_feedback(
    db: Session,
    *,
    kind: str,
    author_user_id: str,
    target_id: str,
    field: str,
    new_value: str,
    reason: str,
    unit: str | None = None,
) -> dict[str, Any]:
    insp = db.get(models.Inspection, target_id)
    original = None
    if insp:
        original = getattr(insp, field, None)
        if original is not None:
            original = str(original)
    token = hashlib.sha256(
        f"{author_user_id}:{target_id}:{field}:{new_value}:{reason}".encode()
    ).hexdigest()[:32]
    return {
        "preview_token": token,
        "kind": kind,
        "target_id": target_id,
        "field": field,
        "original_value": original,
        "new_value": new_value,
        "unit": unit,
        "reason": reason,
        "author_user_id": author_user_id,
        "expected_target_version": 1,
        "impact": {"recalculate": ["production", "spills", "compliance"]},
    }


def apply_feedback(
    db: Session,
    *,
    preview: dict[str, Any],
    author_user_id: str,
) -> dict[str, Any]:
    key = preview["preview_token"]
    existing = (
        db.query(models.Correction)
        .filter(models.Correction.idempotency_key == key)
        .first()
    )
    if existing:
        return {"correction_id": str(existing.id), "status": "idempotent_replay"}

    # supersede prior active correction on same target/field
    priors = (
        db.query(models.Correction)
        .filter(
            models.Correction.target_id == preview["target_id"],
            models.Correction.field == preview["field"],
            models.Correction.status == "active",
        )
        .all()
    )
    for p in priors:
        p.status = "superseded"

    corr = models.Correction(
        target_type="inspection",
        target_id=preview["target_id"],
        field=preview["field"],
        original_value=preview.get("original_value"),
        new_value=str(preview["new_value"]),
        unit=preview.get("unit"),
        author_user_id=author_user_id,
        reason=preview.get("reason") or "",
        scope="inspection",
        status="active",
        idempotency_key=key,
        target_version=preview.get("expected_target_version") or 1,
    )
    db.add(corr)
    db.add(
        models.OutboxEvent(
            event_type="correction_applied",
            payload={"correction_id": str(corr.id), "target_id": corr.target_id},
        )
    )
    kv = db.query(models.KnowledgeVersion).first()
    if kv:
        kv.knowledge_version += 1
    db.commit()
    return {"correction_id": str(corr.id), "status": "applied"}


def record_assertion(
    db: Session,
    *,
    kind: str,
    author_user_id: str,
    text: str,
    asset_id: str | None = None,
    well_type: str | None = None,
    payload: dict[str, Any] | None = None,
    confirmation_state: str = "active",
) -> models.Assertion:
    a = models.Assertion(
        kind=kind,
        author_user_id=author_user_id,
        asset_id=asset_id,
        well_type=well_type,
        text=text,
        payload=payload,
        confirmation_state=confirmation_state,
    )
    db.add(a)
    kv = db.query(models.KnowledgeVersion).first()
    if kv:
        kv.knowledge_version += 1
    db.commit()
    db.refresh(a)
    return a
