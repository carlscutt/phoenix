"""
Closed, registered vocabularies for Module 6 (Business Blueprint Engine).

Per MODULE_06_SPECIFICATION.md §6: the Business Blueprint has a fixed
set of sections — this file is that closed registry, same discipline as
solution_generation/patterns.py (Module 4) and commercial_validation/
categories.py (Module 5). The AI selects/produces content for a section
from this list; it does not invent section names.

BATCH_GROUPS additionally encodes the Build Order's bounded-generation
grouping (Decision 1, approved): six AI calls, not seventeen and not
one — each group gets its own prompt with zero cross-group reasoning
leakage, assembled deterministically afterward in report.py. This
mapping is the single source of truth generator.py iterates over; it is
not duplicated anywhere else.

Extending a group's section list, or adding a new group, is additive
and fine. Renaming or removing a section name already used by a
persisted BusinessBlueprintSection is a breaking change and needs a
migration, not an in-place edit — same rule as every other module's
closed-vocabulary registry.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Canonical order matches spec §6 exactly, top to bottom.
SECTION_NAMES: List[str] = [
    "Executive Summary",
    "Customer Definition",
    "Problem Definition",
    "Value Proposition",
    "Business Model",
    "Lean Canvas",
    "MVP Definition",
    "Product Roadmap",
    "Technical Architecture",
    "Marketing Strategy",
    "Sales Strategy",
    "Financial Overview",
    "Validation Plan",
    "Risks",
    "Success Metrics",
    "90 Day Action Plan",
    "Next Actions",
]

# Six bounded generation groups (Build Order §2, Decision 1). Each
# group is one AI call; generator.py iterates this list in order.
# "label" is descriptive only — not persisted, not shown to the model.
BATCH_GROUPS: List[Dict[str, Any]] = [
    {
        "group": "A",
        "label": "Foundation",
        "sections": ["Executive Summary", "Customer Definition", "Problem Definition"],
    },
    {
        "group": "B",
        "label": "Value & Model",
        "sections": ["Value Proposition", "Business Model", "Lean Canvas"],
    },
    {
        "group": "C",
        "label": "Build",
        "sections": ["MVP Definition", "Product Roadmap", "Technical Architecture"],
    },
    {
        "group": "D",
        "label": "Go-to-Market",
        "sections": ["Marketing Strategy", "Sales Strategy"],
    },
    {
        "group": "E",
        "label": "Numbers & Risk",
        "sections": ["Financial Overview", "Risks", "Validation Plan"],
    },
    {
        "group": "F",
        "label": "Execution",
        "sections": ["Success Metrics", "90 Day Action Plan", "Next Actions"],
    },
]


def is_valid_section_name(value: str) -> bool:
    return value in SECTION_NAMES


def group_for_section(section_name: str) -> str:
    """Returns the group key ('A'-'F') a given section belongs to.
    Raises ValueError for an unregistered section name — callers should
    have already checked is_valid_section_name() if that's a real
    possibility at their call site."""
    for group in BATCH_GROUPS:
        if section_name in group["sections"]:
            return group["group"]
    raise ValueError(f"section_name not in any BATCH_GROUPS entry: {section_name!r}")


def sections_for_group(group_key: str) -> List[str]:
    """Returns the ordered section list for one group ('A'-'F')."""
    for group in BATCH_GROUPS:
        if group["group"] == group_key:
            return group["sections"]
    raise ValueError(f"unknown group key: {group_key!r}")


# Fail fast at import time if BATCH_GROUPS and SECTION_NAMES ever drift
# apart — same "catch a registry mismatch immediately, not at runtime
# deep in a generation call" discipline as every other module's closed
# registries in this project.
_flattened = [s for group in BATCH_GROUPS for s in group["sections"]]
assert len(_flattened) == len(set(_flattened)), "BATCH_GROUPS contains a duplicate section name"
assert set(_flattened) == set(SECTION_NAMES), (
    "BATCH_GROUPS and SECTION_NAMES have drifted apart — "
    f"only in BATCH_GROUPS: {set(_flattened) - set(SECTION_NAMES)}, "
    f"only in SECTION_NAMES: {set(SECTION_NAMES) - set(_flattened)}"
)
