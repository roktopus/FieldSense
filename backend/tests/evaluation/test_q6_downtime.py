"""Acceptance: Q6 top downtime Northeast Block 7 (requires imported sample data)."""

from datetime import date

import pytest
from sqlalchemy import select

from app.analytics.queries import analyze_downtime_by_area
from app.db import models
from app.db.session import SessionLocal


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        wells = session.execute(select(models.Well).limit(1)).scalars().first()
        if wells is None:
            pytest.skip("Sample data not imported")
        yield session
    finally:
        session.close()


def test_q6_top_three_downtime(db):
    result = analyze_downtime_by_area(
        db,
        area_name="Northeast Block 7",
        start=date(2026, 6, 16),
        end_inclusive=date(2026, 10, 16),
        limit=3,
    )
    rows = result["rows"]
    by_id = {r["asset_id"]: r["downtime_days"] for r in rows}
    # Equal 42-day ranks: membership/values matter; order among ties is stable by asset_id.
    assert by_id == {"WELL-0121": 49, "WELL-0138": 42, "WELL-0107": 42}
    assert rows[0]["asset_id"] == "WELL-0121"
    assert rows[0]["downtime_days"] == 49
