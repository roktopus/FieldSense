"""Acceptance coverage for example scenarios Q3–Q18 (requires imported sample data)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agent.orchestrator import _route, run_question
from app.analytics.queries import (
    downtime_for_asset_year,
    non_producing_in_area,
    spill_history,
    spill_heatmap,
    spill_map,
    temperature_series,
)
from app.analytics.rca import wells_needing_rca
from app.compliance.assess import assess_containment_breaches, assess_well_compliance
from app.db import models
from app.db.session import SessionLocal
from app.domain.clock import DEFAULT_AS_OF


AS_OF = DEFAULT_AS_OF
MICHAEL = "U-201"
JESSICA = "U-202"
JAKE = "U-102"
TYLER = "U-204"
LAURA = "U-401"


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        if session.execute(select(models.Well).limit(1)).scalars().first() is None:
            pytest.skip("Sample data not imported")
        yield session
    finally:
        session.close()


def _conv(db, user_id: str) -> uuid.UUID:
    c = models.Conversation(owner_user_id=user_id, title="eval")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c.id


def test_q3_temperature_series_marks_offline(db):
    data = temperature_series(db, "WELL-0001", date(2026, 7, 23), date(2026, 10, 15))
    assert data["count"] == 13
    offline = [p for p in data["points"] if p["status"] == "not_producing"]
    dates = {p["inspected_at"][:10] for p in offline}
    assert "2026-10-08" in dates
    assert "2026-10-15" in dates
    ans = _route(
        db,
        text="Show a line chart of WELL-0001's wellhead temperature against air temperature for the last 13 weeks, and mark when it was not producing oil.",
        user_id=MICHAEL,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    assert ans["kind"] == "line_chart"
    assert len(ans["rows"]) == 13
    assert "2026-10-08" in ans["summary"] and "2026-10-15" in ans["summary"]


def test_q4_spill_history_last_4_years(db):
    data = spill_history(db, "WELL-0001", start=date(2022, 10, 16), end_inclusive=date(2026, 10, 16))
    assert data["effective_spill_count"] == 6
    assert abs(data["known_volume_total"] - 15.1) < 0.05
    assert any(e["inspection_id"] == "INS-0001-0070" for e in data["excluded"])
    ans = _route(
        db,
        text="How many oil spills has WELL-0001 had in the last 4 years, and how much oil in total? List them in a table.",
        user_id=MICHAEL,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    assert ans["kind"] == "table"
    assert ans["data"]["effective_spill_count"] == 6


def test_q5_downtime_2025_with_causes(db):
    data = downtime_for_asset_year(db, "WELL-0001", 2025)
    assert data["downtime_days"] == 21
    assert data["non_producing_count"] == 3
    ans = _route(
        db,
        text="How many days was WELL-0001 down in 2025?",
        user_id=MICHAEL,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    assert "21" in ans["summary"]
    assert ans["visuals"] == []


def test_q7_spill_map_ne8(db):
    data = spill_map(db, "Northeast Block 8", date(2026, 7, 18), date(2026, 10, 16))
    ids = {p["asset_id"] for p in data["pins"]}
    assert ids == {"WELL-0151", "WELL-0165", "WELL-0175", "WELL-0186"}
    assert data["well_count"] == 4


def test_q8_heatmap_totals(db):
    data = spill_heatmap(db, year=2026)
    by_area = {r["area_name"]: r["total"] for r in data["rows"]}
    assert by_area.get("Southwest Block 23") == 35
    assert by_area.get("Southwest Block 24") == 43
    assert by_area.get("Northeast Block 7") == 37
    assert by_area.get("Northeast Block 8") == 26


def test_q9_compliance_breaches(db):
    data = assess_well_compliance(db, "WELL-0001", AS_OF)
    protocols = {b["protocol_id"] for b in data["breaches"]}
    assert "SR-01" in protocols
    assert data["recorded_fines_usd"] >= 5000
    ans = _route(
        db,
        text="Which rules has WELL-0001 broken in the last 12 months, and what is still open?",
        user_id=MICHAEL,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    assert ans["kind"] == "table"
    assert len(ans["rows"]) >= 4


def test_q10_containment_sw24(db):
    data = assess_containment_breaches(
        db,
        area_name="Southwest Block 24",
        start=AS_OF - timedelta(days=90),
        end=AS_OF,
    )
    assets = {b["asset_id"] for b in data["breaches"]}
    assert "WELL-0082" in assets
    assert "WELL-0100" in assets


def test_q11_private_memory_repair_costs(db):
    cid = _conv(db, MICHAEL)
    run_question(
        db,
        user_id=MICHAEL,
        conversation_id=cid,
        text="Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.",
        as_of=AS_OF,
    )
    cid2 = _conv(db, MICHAEL)
    ans = _route(
        db,
        text="For the three wells we discussed yesterday, what have repairs cost this year?",
        user_id=MICHAEL,
        conversation_id=cid2,
        as_of=AS_OF,
        progress=None,
    )
    assert ans["kind"] == "table"
    by_id = {r["asset_id"]: r["cost_usd"] for r in ans["rows"]}
    assert set(by_id) >= {"WELL-0121", "WELL-0138", "WELL-0107"}
    assert abs(by_id["WELL-0121"] - 25794) < 1
    assert abs(by_id["WELL-0138"] - 46942) < 1
    assert abs(by_id["WELL-0107"] - 5176) < 1


def test_q12_thermal_correction_and_q2(db):
    cid = _conv(db, MICHAEL)
    ans = _route(
        db,
        text=(
            "The 15 Oct reading for WELL-0164 is wrong. The handheld thermal gun used in that "
            "inspection was faulty; the field crew re-measured the wellhead at 41.0 °C."
        ),
        user_id=MICHAEL,
        conversation_id=cid,
        as_of=AS_OF,
        progress=None,
    )
    assert "producing" in ans["summary"].lower() or "status=producing" in ans["summary"].lower() or ans["data"]["summary"]["status"] == "producing"
    assert ans.get("conflicts") or "confirm" in ans["summary"].lower() or "Pump jack" in ans["summary"]
    q2 = non_producing_in_area(db, "Northeast Block 8", AS_OF)
    ids = {r["asset_id"] for r in q2["rows"]}
    assert "WELL-0164" not in ids
    assert {"WELL-0170", "WELL-0172", "WELL-0175"} <= ids


def test_q13_spill_volume_correction(db):
    cid = _conv(db, MICHAEL)
    ans = _route(
        db,
        text="The AI estimated the 24 Sep spill at WELL-0151 as 4.5 bbl. The field crew measured 5.4 bbl.",
        user_id=MICHAEL,
        conversation_id=cid,
        as_of=AS_OF,
        progress=None,
    )
    assert "5.4" in ans["summary"]
    assert "SR-01" in ans["summary"]
    assert "SR-03" in ans["summary"]


def test_q14_t350_rca_rule(db):
    before = wells_needing_rca(
        db, area_name="Northeast Block 7", equipment_kind="pump_jack", as_of=AS_OF
    )
    base_ids = {r["asset_id"] for r in before["rows"]}
    assert {"WELL-0108", "WELL-0121", "WELL-0138"} <= base_ids
    assert "WELL-0120" not in base_ids or any(
        r["asset_id"] == "WELL-0120" and "team_rule" in r["rule_provenance"] for r in before["rows"]
    )
    _route(
        db,
        text="Note for all T350 wells: our team now wants a pump jack root-cause analysis after 2 repairs, not 3.",
        user_id=MICHAEL,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    after = wells_needing_rca(
        db, area_name="Northeast Block 7", equipment_kind="pump_jack", as_of=AS_OF
    )
    ids = {r["asset_id"] for r in after["rows"]}
    assert {"WELL-0108", "WELL-0120", "WELL-0121", "WELL-0138"} <= ids
    assert "WELL-0102" not in ids  # T200 with 2 repairs must not appear
    w120 = next(r for r in after["rows"] if r["asset_id"] == "WELL-0120")
    assert "team_rule" in w120["rule_provenance"]


def test_q16_shared_note_and_private_isolation(db):
    _route(
        db,
        text="FYI for everyone: WELL-0007 will be shut in from 17 Oct for a 10-day planned workover.",
        user_id=JAKE,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    ans = _route(
        db,
        text="Is any downtime planned for WELL-0007?",
        user_id=MICHAEL,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    assert "yes" in ans["summary"].lower()
    assert "Jake" in ans["summary"] or "Morales" in ans["summary"]
    # Jessica must not see Michael's Q11 memory
    ans2 = _route(
        db,
        text="For the three wells we discussed yesterday, what have repairs cost this year?",
        user_id=JESSICA,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    assert ans2["kind"] in {"well_picker", "short_answer"}
    assert "private" in ans2["summary"].lower() or "won't use" in ans2["summary"].lower() or "will not use" in ans2["summary"].lower() or "don’t have" in ans2["summary"].lower() or "don't have" in ans2["summary"].lower()


def test_q17_planned_work_and_unconfirmed(db):
    ans = _route(
        db,
        text="WELL-0175 has been shut in for planned work since 14 Oct.",
        user_id=MICHAEL,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    assert "unrecognized_intent" not in str(ans.get("warnings", []))
    assert "WELL-0175" in ans["summary"]
    tyler = _route(
        db,
        text="WELL-0175 is running fine.",
        user_id=TYLER,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    assert "unconfirmed" in tyler["summary"].lower()
    assert "not_producing" in tyler["summary"] or "not producing" in tyler["summary"].lower()
    jake = _route(
        db,
        text="WELL-0001 is back online since 14 Oct.",
        user_id=JAKE,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    assert "unconfirmed" in jake["summary"].lower()


def test_q18_real_oil_conflict(db):
    ans = _route(
        db,
        text="Was the 20 Aug spill at WELL-0101 real oil?",
        user_id=LAURA,
        conversation_id=uuid.uuid4(),
        as_of=AS_OF,
        progress=None,
    )
    assert "yes" in ans["summary"].lower()
    assert ans.get("conflicts")
