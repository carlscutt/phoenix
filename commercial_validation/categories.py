"""
Closed, registered vocabularies for Module 5 (Commercial Validation
Engine). Same discipline as solution_generation/patterns.py (spec §8/§9
equivalent for Module 4): the AI selects from these, it does not invent
categories. Extending a list later is fine (additive); renaming or
removing a value already used by a persisted ValidatedSolutionBlueprint
is a breaking change and needs a migration, not an in-place edit.
"""

from __future__ import annotations

# Spec §10 — every validated solution receives exactly one recommendation.
RECOMMENDATIONS: list[str] = [
    "Reject",
    "Low Priority",
    "Worth Testing",
    "Strong Candidate",
    "Build",
    "Build Immediately",
]

# Spec §13 — confidence reflects evidence quality, never predicts success.
CONFIDENCE_LEVELS: list[str] = [
    "Low",
    "Medium",
    "High",
]


def is_valid_recommendation(value: str) -> bool:
    return value in RECOMMENDATIONS


def is_valid_confidence_level(value: str) -> bool:
    return value in CONFIDENCE_LEVELS
