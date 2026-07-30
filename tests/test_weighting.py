import pytest
from phoenix.scoring.weighting import compute_weighted_score, CATEGORY_WEIGHTS, UNKNOWN


def _all_known(value=50.0):
    return {k: value for k in CATEGORY_WEIGHTS}


def test_all_known_equal_values_returns_that_value():
    score, weights = compute_weighted_score(_all_known(50.0))
    assert score == 50.0
    assert sum(weights.values()) == pytest.approx(100.0)


def test_missing_category_raises():
    values = _all_known()
    del values["frequency"]
    with pytest.raises(ValueError):
        compute_weighted_score(values)


def test_unknown_category_excluded_and_renormalised():
    values = _all_known(80.0)
    values["market_demand"] = UNKNOWN  # 15% weight removed
    score, weights = compute_weighted_score(values)

    assert weights["market_demand"] == 0.0
    assert sum(weights.values()) == pytest.approx(100.0)
    # all remaining categories are equal (80), so renormalised score == 80
    assert score == pytest.approx(80.0)


def test_all_unknown_returns_none():
    values = {k: UNKNOWN for k in CATEGORY_WEIGHTS}
    score, weights = compute_weighted_score(values)
    assert score is None
    assert all(w == 0.0 for w in weights.values())


def test_weighted_mix_matches_hand_calculation():
    values = _all_known(0.0)
    values["frequency"] = 100.0  # weight 20
    values["severity"] = 0.0  # weight 20
    # everything else Unknown
    for k in values:
        if k not in ("frequency", "severity"):
            values[k] = UNKNOWN
    score, weights = compute_weighted_score(values)
    # frequency and severity are equal weight (20 each) -> renormalised to 50/50
    assert weights["frequency"] == pytest.approx(50.0)
    assert weights["severity"] == pytest.approx(50.0)
    # 0.5*100 + 0.5*0 = 50
    assert score == pytest.approx(50.0)
