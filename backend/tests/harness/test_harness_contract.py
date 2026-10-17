"""Harness contract tests — no database. These run on every profile."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.runner import EXPECT_KEYS, _assert_invariants, validate_scenario


def test_validate_rejects_unknown_expect_key(tmp_path: Path):
    spec = {
        "as_of": "2027-01-15T00:00:00Z",
        "turns": [
            {
                "user_id": "U-201",
                "text": "hello",
                "expect": {"kind": "table", "golden_total": 15},
            }
        ],
    }
    with pytest.raises(AssertionError, match="unknown expect keys"):
        validate_scenario(spec, tmp_path / "bad.yaml")


def test_validate_requires_text(tmp_path: Path):
    spec = {"as_of": "2027-01-15T00:00:00Z", "turns": [{"user_id": "U-201", "text": "  "}]}
    with pytest.raises(AssertionError, match="text are required"):
        validate_scenario(spec, tmp_path / "empty.yaml")


def test_final_scenarios_use_only_known_keys():
    root = Path(__file__).parent / "scenarios" / "final"
    paths = list(root.glob("*.yaml"))
    assert len(paths) >= 11
    for path in paths:
        spec = __import__("yaml").safe_load(path.read_text())
        validate_scenario(spec, path)
        assert (spec.get("dataset") or {}).get("min_wells", 0) >= 500


def test_invariant_failure_includes_summary():
    ans = {"kind": "short_answer", "summary": "all good", "rows": None, "visuals": [], "coverage": {}}
    with pytest.raises(AssertionError, match="all good"):
        _assert_invariants(
            ans,
            {"kind": "table"},
            "demo turn 1",
            evidence_count=0,
            prior_assets=set(),
            last_table_rows=None,
        )


def test_followup_must_name_an_earlier_well():
    ans = {
        "kind": "short_answer",
        "summary": "Send a crew first to WELL-0002.",
        "rows": None,
        "visuals": [],
    }
    _assert_invariants(
        ans,
        {"mentions_prior_asset": True},
        "follow-up",
        evidence_count=0,
        prior_assets={"WELL-0002", "WELL-0003"},
        last_table_rows=10,
    )
    with pytest.raises(AssertionError, match="earlier wells"):
        _assert_invariants(
            ans,
            {"mentions_prior_asset": True},
            "follow-up",
            evidence_count=0,
            prior_assets={"WELL-9999"},
            last_table_rows=None,
        )


def test_enum_and_narrower_table():
    rows = [{"status": "Allowed"}, {"status": "Expired"}]
    ans = {"kind": "table", "summary": "ok", "rows": rows, "visuals": [{"kind": "table"}]}
    _assert_invariants(
        ans,
        {"row_values": {"status": ["Allowed", "Expired", "Not approved"]}, "rows_lt_last_table": True},
        "narrow",
        evidence_count=2,
        prior_assets=set(),
        last_table_rows=5,
    )
    with pytest.raises(AssertionError, match="not in"):
        _assert_invariants(
            ans,
            {"row_values": {"status": ["Allowed"]}},
            "narrow",
            evidence_count=0,
            prior_assets=set(),
            last_table_rows=None,
        )


def test_expect_key_set_is_documented():
    assert "mentions_prior_asset" in EXPECT_KEYS
    assert "evidence_min" in EXPECT_KEYS
    assert "rows_lt_last_table" in EXPECT_KEYS
