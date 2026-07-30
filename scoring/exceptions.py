"""Exceptions for Module 3 — Commercial Opportunity Scoring."""


class PhoenixScoringError(Exception):
    """Base class for all Module 3 errors."""


class NoScorableInputError(PhoenixScoringError):
    """Raised when a run has no clusters at all to score (not even one)."""


class ScoringVersionNotFoundError(PhoenixScoringError):
    """Raised when a requested scoring version does not exist for a run."""
