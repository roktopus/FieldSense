"""Acceptance: Q2 non-producing wells in Northeast Block 8 (requires imported sample data)."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.agent.orchestrator import _route
from app.analytics.queries import non_producing_in_area
from app.db import models
from app.db.session import SessionLocal


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        if session.execute(select(models.Well).limit(1)).scalars().first() is None:
            pytest.skip("Sample data not imported")
        yield session
    finally:
        session.close()


def test_q2_query_non_producing_northeast_block_8(db):
    as_of = datetime(2026, 10, 16, tzinfo=timezone.utc)
    data = non_producing_in_area(db, "Northeast Block 8", as_of)
    assert data.get("error") is None
    assert data["count"] >= 1
    assert all(r.get("asset_id", "").startswith("WELL-") for r in data["rows"])


def test_q2_route_table_not_status_crash(db):
    """Regression: 'not producing oil right now' must not hit single-well status."""
    as_of = datetime(2026, 10, 16, tzinfo=timezone.utc)
    q = (
        "Which wells in Northeast Block 8 are not producing oil right now, "
        "and why? Show them in a table."
    )
    result = _route(
        db,
        text=q,
        user_id="U-0003",
        conversation_id=uuid.uuid4(),
        as_of=as_of,
        progress=None,
    )
    assert result["kind"] == "table"
    assert "rows" in result
    assert result.get("error") is None
