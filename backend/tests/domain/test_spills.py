from decimal import Decimal

from app.domain.spills import aggregate_spills


def test_excludes_corrected_detection_from_count_and_volume():
    detections = [
        {"inspection_id": "INS-A", "volume_bbl": Decimal("0.5")},
        {"inspection_id": "INS-RAIN", "volume_bbl": Decimal("1.0")},
        {"inspection_id": "INS-B", "volume_bbl": Decimal("2.6")},
    ]
    result = aggregate_spills(detections, excluded_inspection_ids={"INS-RAIN"})
    assert result.detection_count == 3
    assert result.effective_spill_count == 2
    assert result.known_volume_total == Decimal("3.1")
    assert result.excluded_ids == ["INS-RAIN"]


def test_null_volume_not_treated_as_zero():
    detections = [
        {"inspection_id": "INS-A", "volume_bbl": Decimal("1.5")},
        {"inspection_id": "INS-B", "volume_bbl": None},
    ]
    result = aggregate_spills(detections)
    assert result.known_volume_total == Decimal("1.5")
    assert result.missing_volume_count == 1
    assert result.effective_spill_count == 2
