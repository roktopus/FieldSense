"""End-to-end QA harness for example scenarios Q1–Q18.

Run inside the API container (sample data imported):
  pytest tests/evaluation/qa_scenarios.py -q -s
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.agent.orchestrator import _route, run_question
from app.db import models
from app.db.session import SessionLocal
from app.domain.clock import DEFAULT_AS_OF

# Challenge brief: "Today" is 16 Oct 2026 in 03-evaluation-queries.md (verify both clocks).
AS_OF_16 = datetime(2026, 10, 16, tzinfo=timezone.utc)
AS_OF_17 = datetime(2026, 10, 17, tzinfo=timezone.utc)
AS_OF = DEFAULT_AS_OF  # app default — must match challenge clock after fix

MICHAEL = "U-201"
JESSICA = "U-202"
JAKE = "U-102"
TYLER = "U-204"
LAURA = "U-401"


def _reset_session_state(db):
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
        "outbox_events",
    ]:
        try:
            db.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        except Exception:
            db.rollback()
    db.commit()


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        if session.execute(select(models.Well).limit(1)).scalars().first() is None:
            pytest.skip("Sample data not imported")
        _reset_session_state(session)
        yield session
    finally:
        session.close()


def _ask(db, user_id: str, question: str, as_of=AS_OF) -> dict:
    cid = uuid.uuid4()
    conv = models.Conversation(id=cid, owner_user_id=user_id, title=question[:60])
    db.add(conv)
    db.commit()
    run = run_question(
        db,
        user_id=user_id,
        conversation_id=cid,
        text=question,
        as_of=as_of,
    )
    ans = run.answer_json or {}
    return ans


def _visual_kinds(ans: dict) -> set[str]:
    return {str(v.get("kind")) for v in (ans.get("visuals") or [])}


def _has_evidence(ans: dict) -> bool:
    return bool(ans.get("citations") or ans.get("result_set_id") or ans.get("evidence"))


class TestPartA1FactsVisualsEvidence:
    def test_q1_status_card(self, db):
        ans = _ask(
            db,
            MICHAEL,
            "Is WELL-0001 producing oil right now? When was it last inspected, and by whom? Show me its status card.",
        )
        assert "status_card" in _visual_kinds(ans)
        data = ans.get("data") or {}
        assert data.get("status") == "not_producing"
        li = data.get("latest_inspection") or {}
        assert li.get("inspection_id") == "INS-0001-0203"
        assert "Ryan Brooks" in (li.get("inspector_name") or "")
        assert abs((data.get("delta_c") or 0) - 3.2) < 0.01
        assert data.get("recorded_status_stale") is True
        assert any("CTX-0001-003" in (n.get("note_id") or "") for n in data.get("context_notes") or [])
        assert _has_evidence(ans) or ans.get("result_set_id")

    def test_q2_table_four_wells(self, db):
        ans = _ask(
            db,
            MICHAEL,
            "Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.",
        )
        assert "table" in _visual_kinds(ans)
        ids = {r["asset_id"] for r in ans.get("rows") or []}
        assert ids == {"WELL-0164", "WELL-0170", "WELL-0172", "WELL-0175"}
        by = {r["asset_id"]: r for r in ans["rows"]}
        assert abs(by["WELL-0164"]["delta_c"] - 4.1) < 0.05
        assert "No recorded reason" in by["WELL-0164"]["reason"]
        assert "MNT-0170-031" in by["WELL-0170"]["reason"]
        assert "MNT-0172-028" in by["WELL-0172"]["reason"]
        assert "No recorded reason" in by["WELL-0175"]["reason"]
        assert "suggest" in ans["summary"].lower() or "check" in ans["summary"].lower()

    def test_q3_line_chart(self, db):
        ans = _ask(
            db,
            MICHAEL,
            "Show a line chart of WELL-0001's wellhead temperature against air temperature for the last 13 weeks, and mark when it was not producing oil.",
        )
        assert "line_chart" in _visual_kinds(ans)
        rows = ans.get("rows") or []
        assert len(rows) == 13
        offline = {str(r["inspected_at"])[:10] for r in rows if r.get("status") == "not_producing"}
        assert "2026-10-08" in offline and "2026-10-15" in offline

    def test_q4_spills(self, db):
        ans = _ask(
            db,
            MICHAEL,
            "How many oil spills has WELL-0001 had in the last 4 years, and how much oil in total? List them in a table.",
        )
        assert "table" in _visual_kinds(ans)
        data = ans.get("data") or {}
        assert data.get("effective_spill_count") == 6
        assert abs((data.get("known_volume_total") or 0) - 15.1) < 0.05
        assert any(e.get("inspection_id") == "INS-0001-0070" for e in data.get("excluded") or [])

    def test_q5_downtime_2025(self, db):
        ans = _ask(db, MICHAEL, "How many days was WELL-0001 down in 2025?")
        assert ans.get("visuals") == [] or not _visual_kinds(ans)
        assert "21" in (ans.get("summary") or "")
        assert "MNT-0001-021" in (ans.get("summary") or "") or any(
            (d.get("maintenance_id") == "MNT-0001-021") for d in (ans.get("rows") or [])
        )

    def test_q6_bar_chart(self, db):
        ans = _ask(
            db,
            MICHAEL,
            "Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.",
        )
        assert "bar_chart" in _visual_kinds(ans)
        rows = ans.get("rows") or []
        by = {r["asset_id"]: r["downtime_days"] for r in rows}
        assert by.get("WELL-0121") == 49
        assert by.get("WELL-0107") == 42
        assert by.get("WELL-0138") == 42

    def test_q7_map(self, db):
        ans = _ask(
            db,
            MICHAEL,
            "Show on a map every well in Northeast Block 8 with a real spill in the last 90 days.",
        )
        assert "map" in _visual_kinds(ans)
        ids = {r["asset_id"] for r in ans.get("rows") or []}
        assert ids == {"WELL-0151", "WELL-0165", "WELL-0175", "WELL-0186"}

    def test_q8_heatmap(self, db):
        ans = _ask(db, MICHAEL, "Show a heatmap of 2026 spills by geographic area and month.")
        assert "heatmap" in _visual_kinds(ans)
        by = {r["area_name"]: r["total"] for r in ans.get("rows") or []}
        assert by.get("Southwest Block 23") == 35
        assert by.get("Southwest Block 24") == 43
        assert by.get("Northeast Block 7") == 37
        assert by.get("Northeast Block 8") == 26

    def test_q9_compliance(self, db):
        ans = _ask(
            db,
            MICHAEL,
            "Which rules has WELL-0001 broken in the last 12 months, and what is still open?",
        )
        assert "table" in _visual_kinds(ans)
        protocols = {r.get("protocol_id") for r in ans.get("rows") or []}
        assert {"SR-01", "SR-02", "SR-03", "RC-04"} <= protocols
        assert "5000" in (ans.get("summary") or "").replace(",", "") or "5,000" in (
            ans.get("summary") or ""
        )

    def test_q10_containment(self, db):
        ans = _ask(
            db,
            MICHAEL,
            "In Southwest Block 24, which spills in the last 90 days were not contained within the SOP time limit?",
        )
        assert "table" in _visual_kinds(ans)
        ids = {r["asset_id"] for r in ans.get("rows") or []}
        assert {"WELL-0082", "WELL-0100"} <= ids


class TestPartA2MemoryFeedback:
    def test_q11_private_memory(self, db):
        _ask(
            db,
            MICHAEL,
            "Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.",
        )
        ans = _ask(
            db,
            MICHAEL,
            "For the three wells we discussed yesterday, what have repairs cost this year?",
        )
        assert "table" in _visual_kinds(ans)
        by = {r["asset_id"]: r["cost_usd"] for r in ans.get("rows") or []}
        assert abs(by["WELL-0121"] - 25794) < 1
        assert abs(by["WELL-0138"] - 46942) < 1
        assert abs(by["WELL-0107"] - 5176) < 1

    def test_q12_correction_carries_forward(self, db):
        ans = _ask(
            db,
            MICHAEL,
            "The 15 Oct reading for WELL-0164 is wrong. The handheld thermal gun used in that "
            "inspection was faulty; the field crew re-measured the wellhead at 41.0 °C.",
        )
        assert "producing" in (ans.get("summary") or "").lower() or (
            (ans.get("data") or {}).get("summary") or {}
        ).get("status") == "producing"
        assert "pump jack" in (ans.get("summary") or "").lower() or ans.get("conflicts")
        q2 = _ask(
            db,
            MICHAEL,
            "Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.",
        )
        ids = {r["asset_id"] for r in q2.get("rows") or []}
        assert "WELL-0164" not in ids
        assert {"WELL-0170", "WELL-0172", "WELL-0175"} <= ids

    def test_q13_spill_correction(self, db):
        ans = _ask(
            db,
            MICHAEL,
            "The AI estimated the 24 Sep spill at WELL-0151 as 4.5 bbl. The field crew measured 5.4 bbl.",
        )
        s = ans.get("summary") or ""
        assert "5.4" in s and "SR-01" in s and "SR-03" in s

    def test_q14_team_rule(self, db):
        a = _ask(
            db,
            MICHAEL,
            "Which wells in Northeast Block 7 need a root-cause analysis on their pump jack?",
        )
        ids = {r["asset_id"] for r in a.get("rows") or []}
        # may already include 0120 if rule from prior test; baseline must include these three
        assert {"WELL-0108", "WELL-0121", "WELL-0138"} <= ids
        _ask(
            db,
            MICHAEL,
            "Note for all T350 wells: our team now wants a pump jack root-cause analysis after 2 repairs, not 3.",
        )
        b = _ask(
            db,
            MICHAEL,
            "Which wells in Northeast Block 7 need a root-cause analysis on their pump jack?",
        )
        ids2 = {r["asset_id"] for r in b.get("rows") or []}
        assert {"WELL-0108", "WELL-0120", "WELL-0121", "WELL-0138"} <= ids2
        assert "WELL-0102" not in ids2
        w120 = next(r for r in b["rows"] if r["asset_id"] == "WELL-0120")
        assert "team_rule" in w120["rule_provenance"]


class TestPartBMultiUser:
    def test_q15_shared_corrections(self, db):
        # ensure corrections exist (idempotent if prior tests applied)
        _ask(
            db,
            MICHAEL,
            "The 15 Oct reading for WELL-0164 is wrong. The handheld thermal gun used in that "
            "inspection was faulty; the field crew re-measured the wellhead at 41.0 °C.",
        )
        _ask(
            db,
            MICHAEL,
            "The AI estimated the 24 Sep spill at WELL-0151 as 4.5 bbl. The field crew measured 5.4 bbl.",
        )
        j = _ask(db, JESSICA, "Is WELL-0164 producing oil right now? Show me its status card.")
        assert (j.get("data") or {}).get("status") == "producing"
        assert "Michael" in (j.get("summary") or "") or (j.get("data") or {}).get("applied_corrections")
        l = _ask(
            db,
            LAURA,
            "Which spills in Northeast Block 8 in the last 90 days needed a report to the regulator?",
        )
        rows = l.get("rows") or []
        assert any(r.get("asset_id") == "WELL-0151" for r in rows)
        assert all(r.get("volume_bbl", 0) >= 5 for r in rows)

    def test_q16_shared_vs_private(self, db):
        _ask(
            db,
            JAKE,
            "FYI for everyone: WELL-0007 will be shut in from 17 Oct for a 10-day planned workover.",
        )
        m = _ask(db, MICHAEL, "Is any downtime planned for WELL-0007?")
        assert "yes" in (m.get("summary") or "").lower()
        assert "Jake" in (m.get("summary") or "") or "Morales" in (m.get("summary") or "")
        j = _ask(
            db,
            JESSICA,
            "For the three wells we discussed yesterday, what have repairs cost this year?",
        )
        summary = j.get("summary") or ""
        summary_l = summary.lower()
        assert j.get("kind") == "short_answer"
        assert "don’t have" in summary_l or "don't have" in summary_l or "no such" in summary_l
        # Must not leak Michael's Q11 repair costs (example WELL ids in coaching text are OK).
        assert "25,794" not in summary and "25794" not in summary
        assert "46,942" not in summary and "5,176" not in summary
        assert not (j.get("rows") or [])

    def test_q17_conflicts(self, db):
        _ask(db, MICHAEL, "WELL-0175 has been shut in for planned work since 14 Oct.")
        t = _ask(db, TYLER, "WELL-0175 is running fine.")
        assert "unconfirmed" in (t.get("summary") or "").lower()
        assert "not_producing" in (t.get("summary") or "") or "not producing" in (
            t.get("summary") or ""
        ).lower()
        j = _ask(db, JAKE, "WELL-0001 is back online since 14 Oct.")
        assert "unconfirmed" in (j.get("summary") or "").lower()
        assert "CTX-0001-003" in (j.get("summary") or "") or "20 Oct" in (j.get("summary") or "")

    def test_q18_spill_disagreement(self, db):
        ans = _ask(db, LAURA, "Was the 20 Aug spill at WELL-0101 real oil?")
        assert "yes" in (ans.get("summary") or "").lower()
        assert ans.get("conflicts") or "disagree" in (ans.get("summary") or "").lower()
        assert "INS-0101-0197" in (ans.get("summary") or "")


def test_clock_alignment_documented():
    """Guard: code default matches sample Dataset Guide; env may override for test profile."""
    assert DEFAULT_AS_OF == AS_OF_16
    from app.domain.clock import parse_as_of
    from app.core.config import get_settings

    configured = parse_as_of(None).date()
    profile = get_settings().dataset_profile
    if profile == "test":
        assert configured.isoformat() == "2027-01-15"
    else:
        assert configured == AS_OF_16.date()
