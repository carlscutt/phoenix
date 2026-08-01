"""
Closed, registered vocabularies for Module 4 (Solution Generation Engine).

Per MODULE_04_SPECIFICATION.md v1.3 §8/§9: the AI does not invent
solution types, commercial patterns, or revenue models — it selects
from these lists. This is deliberate: consistent UI rendering, easier
filtering, future analytics, easier scoring, and easier Module 5
validation all depend on these being a controlled vocabulary, not free
text.

Built from the start as one small module rather than retrofitted later,
since Module 5 will need to reference the same registries for its own
validation (Carl, 2026-07-30 review, Recommendation 3).

Extending a list is fine and expected over time (spec §8: "future
categories must remain additive"). Renaming or removing an existing
value is a breaking change to every prior SolutionBlueprint that used
it — that needs a migration, not an in-place edit here.
"""

from __future__ import annotations

SOLUTION_TYPES: list[str] = [
    "Micro SaaS",
    "AI Agent",
    "Browser Extension",
    "Desktop Application",
    "Mobile Application",
    "API",
    "Newsletter",
    "Membership",
    "Marketplace",
    "Prompt Pack",
    "Automation Service",
    "Consulting",
    "Course",
    "Ebook",
]

COMMERCIAL_PATTERNS: list[str] = [
    "Subscription",
    "Freemium",
    "One-Time Purchase",
    "Marketplace",
    "Usage Based",
    "Affiliate",
    "Advertising",
    "Membership",
    "Licensing",
    "Lead Generation",
]

REVENUE_MODELS: list[str] = [
    "Subscription",
    "One-Time Purchase",
    "Usage Based",
    "Freemium",
    "Affiliate Commission",
    "Advertising",
    "Licensing",
    "Marketplace Fee",
    "Lead Generation Fee",
]


def is_valid_solution_type(value: str) -> bool:
    return value in SOLUTION_TYPES


def is_valid_commercial_pattern(value: str) -> bool:
    return value in COMMERCIAL_PATTERNS


def is_valid_revenue_model(value: str) -> bool:
    return value in REVENUE_MODELS
