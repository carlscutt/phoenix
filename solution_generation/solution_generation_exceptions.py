"""
Module 4 (Solution Generation Engine) exceptions.

Same pattern as phoenix/scoring/exceptions.py (NoScorableInputError,
ScoringVersionNotFoundError) — small, specific exception classes per
distinct failure mode, not one generic exception for everything.
"""

from __future__ import annotations


class OpportunityEntryNotFoundError(Exception):
    """Raised when a requested cluster_id has no matching entry in a
    (run_id, scoring_version) score report."""


class InsufficientCommercialEvidenceError(Exception):
    """
    Raised when the selected OpportunityScoreEntry's status is
    "Insufficient Evidence" — per spec §15, generation is never
    attempted in this case; this signals the caller to surface the
    "Insufficient Commercial Evidence" result directly.
    """


class SolutionGenerationVersionNotFoundError(Exception):
    """Raised when a requested SolutionGenerationVersion does not exist
    for the given opportunity."""


class BlueprintNotFoundError(Exception):
    """Raised when approve_blueprint() (or similar) is given a public_id
    that doesn't match any persisted SolutionBlueprint."""
