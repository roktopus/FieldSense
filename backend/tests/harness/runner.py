"""YAML scenario harness.

Practices this runner is built around:

- Scenarios declare invariants (shape, enums, provenance), not memorized totals.
- A scenario file is validated before any turn runs, so a typo fails closed.
- The imported dataset is checked (well count) so a sample database cannot pass the final suite.
- Failures include the actual kind, coverage, and summary — not only the missing needle.
- Multi-turn checks can require a later answer to name a well from an earlier turn,
  and a later table to be a narrower set than the last table in the scenario.
"""

from __future__ import annotations

import json
import re
import uuid
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
FAILURES = Path(__file__).parent / "_failures"
ASSET_RE = re.compile(r"\bWELL-\d{4}\b")

EXPECT_KEYS = {
    "kind",
    "visual_kinds",
    "summary_contains",
    "summary_excludes",
    "rows_min",
    "rows_max",
    "rows_exact",
    "rows_empty",
    "coverage_status",
    "has_conflicts",
    "row_fields",
    "row_values",
    "evidence_min",
    "evidence_max",
    "citations_min",
    "visuals_empty",
    "mentions_prior_asset",
    "rows_lt_last_table",
}


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
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise AssertionError(f"{path.name}: scenario must be a mapping")
    return data


def validate_scenario(spec: dict[str, Any], path: Path) -> None:
    """Fail closed on a malformed scenario before touching the model."""
    if not spec.get("as_of"):
        raise AssertionError(f"{path.name}: missing as_of")
    turns = spec.get("turns")
    if not isinstance(turns, list) or not turns:
        raise AssertionError(f"{path.name}: turns must be a non-empty list")
    dataset = spec.get("dataset") or {}
    if dataset and not isinstance(dataset, dict):
        raise AssertionError(f"{path.name}: dataset must be a mapping")
    for i, turn in enumerate(turns, start=1):
        label = f"{path.name} turn {i}"
        if not isinstance(turn, dict):
            raise AssertionError(f"{label}: turn must be a mapping")
        if not turn.get("user_id") or not str(turn.get("text") or "").strip():
            raise AssertionError(f"{label}: user_id and text are required")
        if turn.get("session", "new") not in ("new", "same"):
            raise AssertionError(f"{label}: session must be new or same")
        expect = turn.get("expect") or {}
        if not isinstance(expect, dict):
            raise AssertionError(f"{label}: expect must be a mapping")
        unknown = set(expect) - EXPECT_KEYS
        if unknown:
            raise AssertionError(f"{label}: unknown expect keys {sorted(unknown)}")


def _rows(ans: dict[str, Any]) -> list[dict[str, Any]]:
    rows = ans.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _assets(ans: dict[str, Any]) -> set[str]:
    found = set(ASSET_RE.findall(ans.get("summary") or ""))
    for row in _rows(ans):
        aid = row.get("asset_id")
        if isinstance(aid, str) and aid.startswith("WELL-"):
            found.add(aid)
    return found


def _evidence_count(db, ans: dict[str, Any]) -> int:
    raw = ans.get("result_set_id")
    if not raw:
        return 0
    try:
        rid = uuid.UUID(str(raw))
    except ValueError:
        return 0
    return (
        db.query(models.EvidenceItem)
        .filter(models.EvidenceItem.result_set_id == rid)
        .count()
    )


def _fail(turn_label: str, message: str, ans: dict[str, Any]) -> None:
    summary = (ans.get("summary") or "").replace("\n", " ")[:360]
    cov = (ans.get("coverage") or {}).get("status")
    cols = list(_rows(ans)[0].keys())[:12] if _rows(ans) else []
    raise AssertionError(
        f"{turn_label}: {message}\n"
        f"  kind={ans.get('kind')!r} coverage={cov!r} rows={len(_rows(ans))} cols={cols}\n"
        f"  summary={summary!r}"
    )


def _assert_invariants(
    ans: dict[str, Any],
    inv: dict[str, Any],
    turn_label: str,
    *,
    evidence_count: int,
    prior_assets: set[str],
    last_table_rows: int | None,
) -> None:
    if "kind" in inv and ans.get("kind") != inv["kind"]:
        _fail(turn_label, f"kind expected {inv['kind']!r}", ans)
    if "visual_kinds" in inv:
        got = {str(v.get("kind")) for v in (ans.get("visuals") or [])}
        for k in inv["visual_kinds"]:
            if k not in got and ans.get("kind") != k:
                _fail(turn_label, f"missing visual {k!r}; have {sorted(got)}", ans)
    summary = ans.get("summary") or ""
    low = summary.lower()
    for needle in inv.get("summary_contains") or []:
        if needle.lower() not in low:
            _fail(turn_label, f"summary missing {needle!r}", ans)
    for needle in inv.get("summary_excludes") or []:
        if needle.lower() in low:
            _fail(turn_label, f"summary unexpectedly contains {needle!r}", ans)
    rows = _rows(ans)
    if inv.get("rows_min") is not None and len(rows) < inv["rows_min"]:
        _fail(turn_label, f"rows {len(rows)} < rows_min {inv['rows_min']}", ans)
    if inv.get("rows_max") is not None and len(rows) > inv["rows_max"]:
        _fail(turn_label, f"rows {len(rows)} > rows_max {inv['rows_max']}", ans)
    if inv.get("rows_exact") is not None and len(rows) != inv["rows_exact"]:
        _fail(turn_label, f"rows {len(rows)} != rows_exact {inv['rows_exact']}", ans)
    if inv.get("rows_empty") and rows:
        _fail(turn_label, "expected no result rows", ans)
    if inv.get("visuals_empty") and (ans.get("visuals") or []):
        _fail(turn_label, "expected no visuals", ans)
    if "coverage_status" in inv:
        cov = (ans.get("coverage") or {}).get("status")
        if cov != inv["coverage_status"]:
            _fail(turn_label, f"coverage {cov!r} != {inv['coverage_status']!r}", ans)
    if inv.get("has_conflicts") and not ans.get("conflicts"):
        _fail(turn_label, "expected conflicts", ans)
    for col in inv.get("row_fields") or []:
        if not rows or col not in rows[0]:
            _fail(turn_label, f"missing column {col!r}", ans)
    allowed = inv.get("row_values") or {}
    for col, choices in allowed.items():
        ok = {str(c) for c in choices}
        for row in rows:
            val = row.get(col)
            if val is None or str(val) not in ok:
                _fail(turn_label, f"column {col} value {val!r} not in {sorted(ok)}", ans)
    if inv.get("evidence_min") is not None and evidence_count < inv["evidence_min"]:
        _fail(turn_label, f"evidence {evidence_count} < evidence_min {inv['evidence_min']}", ans)
    if inv.get("evidence_max") is not None and evidence_count > inv["evidence_max"]:
        _fail(turn_label, f"evidence {evidence_count} > evidence_max {inv['evidence_max']}", ans)
    citations = ans.get("citations") or []
    if inv.get("citations_min") is not None and len(citations) < inv["citations_min"]:
        _fail(turn_label, f"citations {len(citations)} < citations_min {inv['citations_min']}", ans)
    if inv.get("mentions_prior_asset"):
        named = set(ASSET_RE.findall(summary))
        named.update(
            str(r.get("asset_id"))
            for r in rows
            if isinstance(r.get("asset_id"), str)
        )
        if not prior_assets or not (named & prior_assets):
            _fail(
                turn_label,
                f"answer names none of the earlier wells {sorted(prior_assets)[:8]}",
                ans,
            )
    if inv.get("rows_lt_last_table"):
        if last_table_rows is None or not (len(rows) < last_table_rows):
            _fail(
                turn_label,
                f"expected fewer rows than the previous table ({last_table_rows})",
                ans,
            )


def _dump_failure(path: Path, turn_index: int, ans: dict[str, Any]) -> None:
    FAILURES.mkdir(parents=True, exist_ok=True)
    out = FAILURES / f"{path.stem}-turn{turn_index}.json"
    out.write_text(json.dumps(ans, indent=2, default=str))


def run_scenario_file(path: Path) -> None:
    spec = _load_yaml(path)
    validate_scenario(spec, path)
    as_of = parse_as_of(spec.get("as_of"))
    db = SessionLocal()
    try:
        n_wells = db.query(models.Well).count()
        if n_wells == 0:
            pytest.skip("Dataset not imported")
        min_wells = int((spec.get("dataset") or {}).get("min_wells") or 0)
        if min_wells and n_wells < min_wells:
            raise AssertionError(
                f"{path.name}: database has {n_wells} wells; scenario requires at least "
                f"{min_wells}. Import the test dataset before the final harness."
            )
        if spec.get("reset", True):
            _reset_mutable(db)
        sessions: dict[str, uuid.UUID] = {}
        prior_by_key: dict[str, set[str]] = {}
        last_table_rows: int | None = None
        for i, turn in enumerate(spec.get("turns") or [], start=1):
            user_id = turn["user_id"]
            mode = turn.get("session", "new")
            key = turn.get("session_key") or user_id
            label = f"{path.name} turn {i}"
            if mode == "new" or key not in sessions:
                cid = uuid.uuid4()
                db.add(
                    models.Conversation(
                        id=cid,
                        owner_user_id=user_id,
                        title=str(turn.get("text", ""))[:60],
                    )
                )
                db.commit()
                sessions[key] = cid
                prior_by_key[key] = set()
            cid = sessions[key]
            run = run_question(
                db,
                user_id=user_id,
                conversation_id=cid,
                text=turn["text"],
                as_of=as_of,
            )
            ans = dict(run.answer_json or {})
            if not ans.get("kind") and run.result_set_id:
                rs = db.get(models.ResultSet, run.result_set_id)
                if rs:
                    ans = {**(rs.payload or {}), **ans, "kind": rs.kind}
            try:
                _assert_invariants(
                    ans,
                    turn.get("expect") or {},
                    label,
                    evidence_count=_evidence_count(db, ans),
                    prior_assets=set(prior_by_key.get(key) or []),
                    last_table_rows=last_table_rows,
                )
            except AssertionError:
                _dump_failure(path, i, ans)
                raise
            prior_by_key.setdefault(key, set()).update(_assets(ans))
            if _rows(ans):
                last_table_rows = len(_rows(ans))
    finally:
        db.close()


def scenario_paths(profile: str) -> list[Path]:
    root = SCENARIO_ROOT / profile
    if not root.is_dir():
        return []
    return sorted(root.glob("*.yaml"))
