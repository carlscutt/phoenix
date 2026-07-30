"""
Weighted sum with Unknown-aware renormalisation (§9 of the architecture spec).

When a category is "Unknown" for a cluster, it is excluded from that
cluster's weighted sum and the remaining weights are renormalised to sum
to 100% before computing overall_score. weights_applied is returned
alongside so the report shows exactly which categories contributed.
"""

from __future__ import annotations

from typing import Dict, Union

Value = Union[float, str]  # str is only ever the literal "Unknown"

CATEGORY_WEIGHTS: Dict[str, float] = {
    "frequency": 20.0,
    "severity": 20.0,
    "evidence_confidence": 10.0,
    "market_demand": 15.0,
    "revenue_potential": 10.0,
    "competition_saturation": 10.0,
    "automation_potential": 10.0,
    "time_to_first_revenue": 5.0,
}

assert abs(sum(CATEGORY_WEIGHTS.values()) - 100.0) < 1e-9, "category weights must sum to 100"

UNKNOWN = "Unknown"


def compute_weighted_score(category_values: Dict[str, Value]) -> tuple[float | None, Dict[str, float]]:
    """
    Compute the renormalised weighted overall score.

    Args:
        category_values: mapping of the 8 category keys (must match
            CATEGORY_WEIGHTS) to either a numeric 0-100 value or the
            literal string "Unknown".

    Returns:
        (overall_score, weights_applied)
        overall_score is None only when every category is Unknown
        (should be rare/impossible given Frequency and Evidence
        Confidence are always deterministic and never Unknown, but
        handled defensively).
        weights_applied maps category -> the renormalised weight that
        was actually used for that entry (0.0 for any Unknown category).
    """
    missing = set(CATEGORY_WEIGHTS) - set(category_values)
    if missing:
        raise ValueError(f"missing category values: {sorted(missing)}")

    known = {
        k: v for k, v in category_values.items() if v != UNKNOWN and v is not None
    }

    if not known:
        return None, {k: 0.0 for k in CATEGORY_WEIGHTS}

    known_weight_total = sum(CATEGORY_WEIGHTS[k] for k in known)

    weights_applied: Dict[str, float] = {}
    weighted_sum = 0.0
    for key, base_weight in CATEGORY_WEIGHTS.items():
        if key in known:
            renormalised = (base_weight / known_weight_total) * 100.0
            weights_applied[key] = round(renormalised, 4)
            weighted_sum += renormalised * float(known[key]) / 100.0
        else:
            weights_applied[key] = 0.0

    return round(weighted_sum, 2), weights_applied
