"""Private user preferences and session topic memory helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db import models


def get_pref(db: Session, user_id: str, key: str) -> dict[str, Any] | None:
    row = (
        db.query(models.UserPreference)
        .filter(models.UserPreference.user_id == user_id, models.UserPreference.key == key)
        .first()
    )
    return dict(row.value) if row else None


def set_pref(db: Session, user_id: str, key: str, value: dict[str, Any]) -> None:
    row = (
        db.query(models.UserPreference)
        .filter(models.UserPreference.user_id == user_id, models.UserPreference.key == key)
        .first()
    )
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(models.UserPreference(user_id=user_id, key=key, value=value))
    db.commit()


def apply_list_prefs(db: Session, user_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pref = get_pref(db, user_id, "list_display") or {}
    out = list(rows)
    if pref.get("sort") == "area_then_well":
        out.sort(key=lambda r: (r.get("area_name") or "", r.get("asset_id") or ""))
    if pref.get("costs_in_thousands"):
        for r in out:
            if "cost_usd" in r and r["cost_usd"] is not None:
                r["cost_usd_k"] = round(float(r["cost_usd"]) / 1000.0, 2)
                r["cost_display"] = f"{r['cost_usd_k']}k"
    return out


def remember_topic(
    db: Session,
    *,
    user_id: str,
    conversation_id: uuid.UUID,
    label: str,
    asset_ids: list[str],
    topic: str,
) -> None:
    db.add(
        models.ConversationReference(
            owner_user_id=user_id,
            conversation_id=conversation_id,
            label=label,
            asset_ids=asset_ids,
            query_spec={"topic": topic},
            discussed_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def topics_today(db: Session, user_id: str, conversation_id: uuid.UUID | None = None) -> list[models.ConversationReference]:
    today = datetime.now(timezone.utc).date()
    q = db.query(models.ConversationReference).filter(
        models.ConversationReference.owner_user_id == user_id
    )
    if conversation_id:
        q = q.filter(models.ConversationReference.conversation_id == conversation_id)
    refs = q.order_by(models.ConversationReference.discussed_at.desc()).all()
    return [
        r
        for r in refs
        if r.discussed_at and r.discussed_at.astimezone(timezone.utc).date() == today
    ]


def assets_talked_about_today(db: Session, user_id: str, conversation_id: uuid.UUID) -> list[str]:
    seen: list[str] = []
    for ref in topics_today(db, user_id, conversation_id):
        for a in ref.asset_ids or []:
            if a not in seen:
                seen.append(a)
    return seen
