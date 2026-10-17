"""YAML scenario harness — turn-based invariants without hardcoding answers in app code."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import text

from app.agent.orchestrator import run_question
from app.db import models
from app.db.session import SessionLocal
from app.domain.clock import parse_as_of


SCENARIO_ROOT = Path(__file__).parent / "scenarios"


def _reset_mutable(db) -> None:
    for table in [
        "evidence_items",
        "result_sets",
        "messages",
        "runs",
        "conversation_references",
        "conversations",
        "corrections",
        "assertions",
        "rule_overrides",
        "user_preferences",
        "outbox_events",
    ]:
        try:
            db.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        except Exception:
            db.rollback()
    db.commit()


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _assert_invariants(ans: dict[str, Any], inv: dict[str, Any], turn_label: str) -> None:
    if "kind" in inv:
        assert ans.get("kind") == inv["kind"], f"{turn_label}: kind"
    if "visual_kinds" in inv:
        got = {str(v.get("kind")) for v in (ans.get("visuals") or [])}
        for k in inv["visual_kinds"]:
            assert k in got or ans.get("kind") == k, f"{turn_label}: missing visual {k}"
    summary = ans.get("summary") or ""
    for needle in inv.get("summary_contains", []) or []:
        assert needle.lower() in summary.lower(), f"{turn_label}: missing '{needle}' in summary"
    for needle in inv.get("summary_excludes", []) or []:
        assert needle.lower() not in summary.lower(), f"{turn_label}: unexpected '{needle}' in summary"
    if inv.get("rows_min") is not None:
        assert len(ans.get("rows") or []) >= inv["rows_min"], f"{turn_label}: rows_min"
    if inv.get("rows_empty"):
        assert not (ans.get("rows") or []), f"{turn_label}: expected empty rows"
    if "coverage_status" in inv:
        cov = ans.get("coverage") or {}
        assert cov.get("status") == inv["coverage_status"], f"{turn_label}: coverage"
    if inv.get("has_conflicts"):
        assert ans.get("conflicts"), f"{turn_label}: expected conflicts"
    for col in inv.get("row_fields", []) or []:
        rows = ans.get("rows") or []
        assert rows, f"{turn_label}: no rows for field check"
        assert col in rows[0], f"{turn_label}: missing column {col}"


def run_scenario_file(path: Path) -> None:
    spec = _load_yaml(path)
    as_of = parse_as_of(spec.get("as_of"))
    db = SessionLocal()
    try:
        if db.query(models.Well).limit(1).first() is None:
            pytest.skip("Dataset not imported")
        if spec.get("reset", True):
            _reset_mutable(db)
        sessions: dict[str, uuid.UUID] = {}
        for i, turn in enumerate(spec.get("turns") or [], start=1):
            user_id = turn["user_id"]
            mode = turn.get("session", "new")
            key = turn.get("session_key") or user_id
            if mode == "new" or key not in sessions:
                cid = uuid.uuid4()
                db.add(
                    models.Conversation(
                        id=cid,
                        owner_user_id=user_id,
                        title=turn.get("text", "")[:60],
                    )
                )
                db.commit()
                sessions[key] = cid
            else:
                cid = sessions[key]
            run = run_question(
                db,
                user_id=user_id,
                conversation_id=cid,
                text=turn["text"],
                as_of=as_of,
            )
            ans = run.answer_json or {}
            # Merge kind from result set if needed
            if not ans.get("kind") and run.result_set_id:
                rs = db.get(models.ResultSet, run.result_set_id)
                if rs:
                    ans = {**(rs.payload or {}), **ans, "kind": rs.kind}
            _assert_invariants(ans, turn.get("expect") or {}, f"{path.name} turn {i}")
    finally:
        db.close()


def scenario_paths(profile: str) -> list[Path]:
    root = SCENARIO_ROOT / profile
    if not root.is_dir():
        return []
    return sorted(root.glob("*.yaml"))
