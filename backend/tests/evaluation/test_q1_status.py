from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.analytics.queries import get_well_summary
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


def test_q1_well_0001_not_producing(db):
    as_of = datetime(2026, 10, 17, tzinfo=timezone.utc)
    summary = get_well_summary(db, "WELL-0001", as_of)
    assert summary["status"] == "not_producing"
    assert summary["latest_inspection"]["inspection_id"] == "INS-0001-0203"
    assert summary["latest_inspection"]["inspector_name"] == "Ryan Brooks"
    assert abs(summary["delta_c"] - 3.2) < 0.01
    assert summary["recorded_status_stale"] is True
    note_ids = {n["note_id"] for n in summary["context_notes"]}
    assert "CTX-0001-003" in note_ids
