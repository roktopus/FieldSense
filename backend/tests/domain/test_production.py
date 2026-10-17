"""TDD: production status from wellhead ΔT vs manual thresholds."""

from decimal import Decimal

from app.domain.production import ProductionStatus, classify_production


def test_t200_producing_when_delta_equals_threshold():
    result = classify_production(
        wellhead_c=Decimal("34.9"),
        ambient_c=Decimal("19.9"),
        well_type="T200",
    )
    assert result.status == ProductionStatus.PRODUCING
    assert result.delta_c == Decimal("15.0")
    assert result.threshold_c == Decimal("15")


def test_t200_not_producing_below_threshold():
    result = classify_production(
        wellhead_c=Decimal("25.6"),
        ambient_c=Decimal("22.4"),
        well_type="T200",
    )
    assert result.status == ProductionStatus.NOT_PRODUCING
    assert result.delta_c == Decimal("3.2")


def test_t350_requires_20c():
    cool = classify_production(Decimal("39.0"), Decimal("20.0"), "T350")
    assert cool.status == ProductionStatus.NOT_PRODUCING
    warm = classify_production(Decimal("40.0"), Decimal("20.0"), "T350")
    assert warm.status == ProductionStatus.PRODUCING
    assert warm.threshold_c == Decimal("20")


def test_missing_temps_unknown():
    result = classify_production(None, Decimal("20"), "T200")
    assert result.status == ProductionStatus.UNKNOWN


def test_unknown_well_type_unknown():
    result = classify_production(Decimal("40"), Decimal("20"), "T999")
    assert result.status == ProductionStatus.UNKNOWN


def test_hot_ambient_does_not_imply_producing():
    # Q5: 51.6 vs 43.1 = 8.5 < 15
    result = classify_production(Decimal("51.6"), Decimal("43.1"), "T200")
    assert result.status == ProductionStatus.NOT_PRODUCING
    assert result.delta_c == Decimal("8.5")
