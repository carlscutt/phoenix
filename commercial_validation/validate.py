"""
phoenix/commercial_validation/validate.py

Validation Output Validation — mirrors Module 4's Blueprint Validation
(spec §6b equivalent for Module 5): checks each AI-produced validation
result before it's ever persisted. Genuinely rejects malformed output,
does not coerce it into looking valid.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from phoenix.commercial_validation.categories import (
    is_valid_recommendation,
    is_valid_confidence_level,
)
from phoenix.commercial_validation.validator import SCORE_FIELDS

REQUIRED_LIST_FIELDS: List[str] = ["strengths", "weaknesses", "primary_risks", "suggested_improvements"]
SCORE_MIN, SCORE_MAX = 0, 100


def _errors_for_one(result: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    for field in SCORE_FIELDS:
        value = result.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{field} missing or not numeric")
        elif not (SCORE_MIN <= value <= SCORE_MAX):
            errors.append(f"{field} out of range {SCORE_MIN}-{SCORE_MAX}: {value}")

    recommendation = result.get("overall_recommendation")
    if not is_valid_recommendation(recommendation):
        errors.append(f"overall_recommendation not in closed registry: {recommendation!r}")

    confidence = result.get("validation_confidence")
    if not is_valid_confidence_level(confidence):
        errors.append(f"validation_confidence not in closed registry: {confidence!r}")

    explanation = result.get("validation_explanation")
    if not explanation or not isinstance(explanation, str):
        errors.append("validation_explanation missing or empty")

    for field in REQUIRED_LIST_FIELDS:
        value = result.get(field)
        if not isinstance(value, list):
            errors.append(f"{field} missing or not a list")

    return errors


def validate_results(results: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    results: one validate_blueprint() output dict per blueprint, each
    already tagged with its solution_public_id by report.py before this
    is called. This function only checks shape — it's agnostic to which
    blueprint a result belongs to.

    Returns (accepted, rejected) — same accepted/rejected split pattern
    as Module 4's validate_candidates(). Rejected entries carry their
    original content plus a "_validation_errors" list, for logging.
    """
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for result in results:
        errors = _errors_for_one(result)
        if errors:
            rejected.append({**result, "_validation_errors": errors})
        else:
            accepted.append(result)
    return accepted, rejected
