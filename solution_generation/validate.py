"""
Module 4 (Solution Generation Engine) — Blueprint Validation.

Per MODULE_04_SPECIFICATION.md v1.3 §6b: a discrete step between
generator.py's raw output and report.py's persistence call. Candidates
failing validation are dropped and logged, never coerced into passing
and never persisted. This mirrors the same "validate before persisting"
discipline used elsewhere in Phoenix (theming.py's theme-count checks,
ai_scoring.py's structured-output checks).

Deliberately separate from generator.py (Build Order §4.5): "was the
model's JSON well-formed" (generator.py's job) and "is this a
business-valid blueprint" (this file's job) are different questions,
tested independently.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from phoenix.solution_generation.patterns import (
    is_valid_solution_type,
    is_valid_commercial_pattern,
    is_valid_revenue_model,
)

REQUIRED_FIELDS = (
    "working_title",
    "solution_type",
    "estimated_customer_type",
    "target_customer",
    "customer_problem",
    "value_proposition",
    "commercial_patterns",
    "revenue_model",
    "delivery_model",
    "pricing_strategy",
    "automation_potential",
    "estimated_build_complexity",
    "estimated_time_to_mvp",
    "required_skills",
    "primary_risks",
    "key_assumptions",
    "confidence",
    "reasoning",
)

VALID_CONFIDENCE = ("Low", "Medium", "High")


def _validate_one(candidate: Dict[str, Any]) -> Tuple[bool, str]:
    """Returns (is_valid, reason_if_not)."""
    missing = [f for f in REQUIRED_FIELDS if f not in candidate or candidate[f] in (None, "", [])]
    if missing:
        return False, f"missing required fields: {missing}"

    if not is_valid_solution_type(candidate["solution_type"]):
        return False, f"solution_type not in registry: {candidate['solution_type']!r}"

    patterns = candidate["commercial_patterns"]
    if not isinstance(patterns, list) or not patterns:
        return False, "commercial_patterns must be a non-empty list"
    invalid_patterns = [p for p in patterns if not is_valid_commercial_pattern(p)]
    if invalid_patterns:
        return False, f"commercial_patterns not in registry: {invalid_patterns}"

    if not is_valid_revenue_model(candidate["revenue_model"]):
        return False, f"revenue_model not in registry: {candidate['revenue_model']!r}"

    if candidate["confidence"] not in VALID_CONFIDENCE:
        return False, f"confidence not one of {VALID_CONFIDENCE}: {candidate['confidence']!r}"

    reasoning = candidate["reasoning"]
    if not isinstance(reasoning, dict):
        return False, "reasoning must be a dict"
    reasoning_fields = ("why_fits", "evidence_support", "unverified_assumptions", "why_alternative")
    missing_reasoning = [f for f in reasoning_fields if not reasoning.get(f)]
    if missing_reasoning:
        return False, f"reasoning missing fields: {missing_reasoning}"

    return True, ""


def _is_duplicate(candidate: Dict[str, Any], accepted: List[Dict[str, Any]]) -> bool:
    """
    Same Solution Type + same Working Title, or a materially identical
    Value Proposition, counts as a duplicate within one generation run
    (spec §6b) — the diversity requirement (§12) cuts both ways: reject
    near-duplicates, don't just accept too few.
    """
    for a in accepted:
        if (
            a["solution_type"] == candidate["solution_type"]
            and a["working_title"].strip().lower() == candidate["working_title"].strip().lower()
        ):
            return True
        if a["value_proposition"].strip().lower() == candidate["value_proposition"].strip().lower():
            return True
    return False


def validate_candidates(
    candidates: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validate a list of raw candidate blueprints from generator.py.

    Returns (accepted, rejected) — accepted candidates are ready for
    audit-hash + persistence (Build Order steps 5-6); rejected entries
    are [{"candidate": ..., "reason": ...}] for logging, never persisted.

    This function does NOT enforce the §12 diversity minimum (3-5) by
    itself — it only filters. The caller (report.py orchestrator,
    Build Order step 6) decides what "too few survived validation"
    means (routes to the same §15 Insufficient Commercial Evidence
    outcome as too little evidence in the first place).
    """
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for candidate in candidates:
        is_valid, reason = _validate_one(candidate)
        if not is_valid:
            rejected.append({"candidate": candidate, "reason": reason})
            continue
        if _is_duplicate(candidate, accepted):
            rejected.append({"candidate": candidate, "reason": "duplicate within this run"})
            continue
        accepted.append(candidate)

    return accepted, rejected
