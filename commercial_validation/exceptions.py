"""
phoenix/commercial_validation/exceptions.py

Module 5's own exception types. Mirrors solution_generation/exceptions.py
naming style.
"""

from __future__ import annotations


class BlueprintSetNotFoundError(Exception):
    """Raised when no SolutionBlueprint set exists yet for the requested
    opportunity — Module 5 never generates blueprints itself (spec §3,
    §21), so this tells the caller to run Module 4 first."""


class InsufficientValidationEvidenceError(Exception):
    """Raised when validation was attempted but produced no usable,
    Validation-Output-Validation-passing results (spec §16 pattern,
    mirrored from Module 4's Insufficient Commercial Evidence)."""


class ValidationVersionNotFoundError(Exception):
    """Raised when a specific ValidationVersion row can't be located
    during persistence or lookup."""
