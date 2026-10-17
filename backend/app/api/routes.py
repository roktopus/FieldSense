from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.evidence_synth import synthesize_evidence
from app.agent.orchestrator import run_question
from app.api.deps import get_clock, get_current_user, get_session_id
from app.db import models
from app.db.session import get_db
from app.feedback.service import apply_feedback, preview_feedback

router = APIRouter()


class SessionUserBody(BaseModel):
    user_id: str


class ConversationCreate(BaseModel):
    title: str = "New chat"


class RunCreate(BaseModel):
    message: str = Field(min_length=1)


class FeedbackPreviewBody(BaseModel):
    kind: str
    target_id: str
    field: str
    new_value: str
    reason: str
    unit: str | None = None


class FeedbackApplyBody(BaseModel):
    preview: dict[str, Any]


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Annotated[Session, Depends(get_db)]):
    db.execute(select(1))
    return {"status": "ready"}


@router.get("/api/v1/users")
def list_users(db: Annotated[Session, Depends(get_db)]):
    users = db.execute(select(models.User).order_by(models.User.name)).scalars().all()
    return {
        "users": [
            {
                "user_id": u.user_id,
                "name": u.name,
                "role": u.role,
                "team_id": u.team_id,
            }
            for u in users
        ],
        "demo_identity": True,
        "note": "Demo identity selection — not production authentication",
    }


@router.post("/api/v1/session/user")
def select_user(
    body: SessionUserBody,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    session_id: Annotated[str, Depends(get_session_id)],
):
    user = db.get(models.User, body.user_id)
    if not user:
        raise HTTPException(404, "Unknown user")
    sess = db.get(models.DemoSession, session_id)
    if sess is None:
        sess = models.DemoSession(id=session_id, user_id=body.user_id, session_generation=1)
        db.add(sess)
    else:
        sess.user_id = body.user_id
        sess.session_generation += 1
    db.commit()
    response.set_cookie("fieldsense_session", session_id, httponly=True, samesite="lax")
    return {
        "user_id": user.user_id,
        "name": user.name,
        "role": user.role,
        "session_generation": sess.session_generation,
        "session_id": session_id,
    }


@router.get("/api/v1/conversations")
def list_conversations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[tuple[str, int, str], Depends(get_current_user)],
):
    user_id, _, _ = user
    rows = db.execute(
        select(models.Conversation)
        .where(models.Conversation.owner_user_id == user_id)
        .order_by(models.Conversation.updated_at.desc())
    ).scalars().all()
    return {
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in rows
        ]
    }


@router.post("/api/v1/conversations")
def create_conversation(
    body: ConversationCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[tuple[str, int, str], Depends(get_current_user)],
):
    user_id, _, _ = user
    conv = models.Conversation(owner_user_id=user_id, title=body.title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"id": str(conv.id), "title": conv.title}


@router.get("/api/v1/conversations/{conversation_id}")
def get_conversation(
    conversation_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[tuple[str, int, str], Depends(get_current_user)],
):
    user_id, _, _ = user
    conv = db.get(models.Conversation, conversation_id)
    if not conv or conv.owner_user_id != user_id:
        raise HTTPException(404, "Not found")
    messages = db.execute(
        select(models.Message)
        .where(models.Message.conversation_id == conversation_id)
        .order_by(models.Message.created_at.asc())
    ).scalars().all()
    return {
        "id": str(conv.id),
        "title": conv.title,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "answer": m.answer_json,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.post("/api/v1/conversations/{conversation_id}/runs")
def start_run(
    conversation_id: uuid.UUID,
    body: RunCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[tuple[str, int, str], Depends(get_current_user)],
    clock=Depends(get_clock),
):
    user_id, generation, _ = user
    conv = db.get(models.Conversation, conversation_id)
    if not conv or conv.owner_user_id != user_id:
        raise HTTPException(404, "Not found")
    run = run_question(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        text=body.message,
        as_of=clock,
        session_generation=generation,
    )
    return {"run_id": str(run.id), "status": run.status, "answer": run.answer_json}


@router.get("/api/v1/runs/{run_id}")
def get_run(
    run_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[tuple[str, int, str], Depends(get_current_user)],
):
    user_id, _, _ = user
    run = db.get(models.Run, run_id)
    if not run or run.owner_user_id != user_id:
        raise HTTPException(404, "Not found")
    return {
        "run_id": str(run.id),
        "status": run.status,
        "answer": run.answer_json,
        "error": run.error,
    }


@router.get("/api/v1/results/{result_id}/rows")
def result_rows(
    result_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[tuple[str, int, str], Depends(get_current_user)],
    offset: int = 0,
    limit: int = 50,
):
    user_id, _, _ = user
    rs = db.get(models.ResultSet, result_id)
    if not rs or (rs.owner_user_id and rs.owner_user_id != user_id):
        raise HTTPException(404, "Not found")
    rows = rs.payload.get("rows") or rs.payload.get("data", {}).get("rows") or []
    if not isinstance(rows, list):
        rows = []
    return {"rows": rows[offset : offset + limit], "total": len(rows)}


@router.get("/api/v1/evidence")
def list_evidence(
    result_set_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[tuple[str, int, str], Depends(get_current_user)],
    offset: int = 0,
    limit: int = 100,
):
    user_id, _, _ = user
    rs = db.get(models.ResultSet, result_set_id)
    if not rs or (rs.owner_user_id and rs.owner_user_id != user_id):
        raise HTTPException(404, "Not found")
    limit = min(max(limit, 1), 200)
    items = db.execute(
        select(models.EvidenceItem)
        .where(models.EvidenceItem.result_set_id == result_set_id)
        .offset(offset)
        .limit(limit)
    ).scalars().all()
    total = (
        db.query(models.EvidenceItem)
        .filter(models.EvidenceItem.result_set_id == result_set_id)
        .count()
    )
    # Fallback: synthesize from payload for older result sets that stored empty evidence[]
    if not items and rs.payload:
        payload = rs.payload or {}
        # Honest coverage refusals have no source records to show
        if (payload.get("coverage") or {}).get("status") == "unsupported":
            return {"items": [], "total": 0}
        raw = list(payload.get("evidence") or [])
        if not raw:
            raw = synthesize_evidence(
                rows=payload.get("rows") if isinstance(payload.get("rows"), list) else [],
                citations=payload.get("citations") if isinstance(payload.get("citations"), list) else [],
                db=db,
                limit=limit,
            )
        synthesized = [
            {
                "id": None,
                "kind": ev.get("kind", "record"),
                "source_id": ev.get("source_id"),
                "source_path": ev.get("source_path"),
                "locator": ev.get("locator"),
                "title": ev.get("title"),
                "excerpt": ev.get("excerpt"),
                "meta": ev.get("meta"),
            }
            for ev in raw[:limit]
        ]
        return {"items": synthesized, "total": len(synthesized)}
    return {
        "items": [
            {
                "id": str(i.id),
                "kind": i.kind,
                "source_id": i.source_id,
                "source_path": i.source_path,
                "locator": i.locator,
                "title": i.title,
                "excerpt": i.excerpt,
                "meta": i.meta,
            }
            for i in items
        ],
        "total": total,
    }


@router.get("/api/v1/wells")
def search_wells(
    db: Annotated[Session, Depends(get_db)],
    q: str = "",
    limit: int = 50,
):
    stmt = select(models.Well).order_by(models.Well.asset_id).limit(limit)
    if q:
        stmt = (
            select(models.Well)
            .where(
                (models.Well.asset_id.ilike(f"%{q}%")) | (models.Well.name.ilike(f"%{q}%"))
            )
            .order_by(models.Well.asset_id)
            .limit(limit)
        )
    wells = db.execute(stmt).scalars().all()
    return {
        "wells": [
            {
                "asset_id": w.asset_id,
                "name": w.name,
                "well_type": w.well_type,
                "area_id": w.area_id,
            }
            for w in wells
        ]
    }


@router.get("/api/v1/areas")
def list_areas(db: Annotated[Session, Depends(get_db)]):
    areas = db.execute(select(models.Area).order_by(models.Area.name)).scalars().all()
    return {
        "areas": [
            {"area_id": a.area_id, "name": a.name, "team_id": a.team_id} for a in areas
        ]
    }


@router.post("/api/v1/feedback/preview")
def feedback_preview(
    body: FeedbackPreviewBody,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[tuple[str, int, str], Depends(get_current_user)],
):
    user_id, _, _ = user
    return preview_feedback(
        db,
        kind=body.kind,
        author_user_id=user_id,
        target_id=body.target_id,
        field=body.field,
        new_value=body.new_value,
        reason=body.reason,
        unit=body.unit,
    )


@router.post("/api/v1/feedback/apply")
def feedback_apply(
    body: FeedbackApplyBody,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[tuple[str, int, str], Depends(get_current_user)],
):
    user_id, _, _ = user
    return apply_feedback(db, preview=body.preview, author_user_id=user_id)


@router.get("/api/v1/import/latest")
def latest_import(db: Annotated[Session, Depends(get_db)]):
    from app.core.config import get_settings
    from app.domain.clock import parse_as_of

    settings = get_settings()
    batch = db.execute(
        select(models.ImportBatch).order_by(models.ImportBatch.started_at.desc()).limit(1)
    ).scalar_one_or_none()
    clock = parse_as_of(None)
    base = {
        "evaluation_as_of": clock.isoformat().replace("+00:00", "Z"),
        "dataset_profile": settings.dataset_profile,
    }
    if not batch:
        return {"status": "none", **base}
    return {
        "id": str(batch.id),
        "status": batch.status,
        "dataset_version": batch.dataset_version,
        "summary": batch.summary,
        "finished_at": batch.finished_at.isoformat() if batch.finished_at else None,
        **base,
    }
