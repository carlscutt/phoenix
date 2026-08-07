"""
Module 6 (Business Blueprint Engine) exceptions.

Same pattern as solution_generation/exceptions.py and
commercial_validation/exceptions.py — small, specific exception classes
per distinct failure mode, not one generic exception for everything.

Delivered alongside fetch_validated_blueprint.py (Build Order Step 3)
rather than strictly after it — the fetch layer needs these to raise,
same practical bundling Modules 4 and 5 both did between their own
fetch layer and exceptions.py.
"""

from __future__ import annotations


class ValidatedBlueprintNotFoundError(Exception):
    """
    Raised when no active ValidationVersion exists for the given
    (run_id, cluster_id), or when one exists but contains no
    ValidatedSolutionBlueprint matching the requested solution_public_id.
    Tells the caller to run Module 5 (Validate Solutions) first, or to
    check the solution_public_id, same shape as Module 5's own
    BlueprintSetNotFoundError telling callers to run Module 4 first.
    """


class SolutionNotFoundError(Exception):
    """
    Raised when Module 5 has a validated result for a solution_public_id
    (i.e. ValidatedBlueprintNotFoundError did NOT fire), but Module 4's
    own get_active_solutions() no longer has a matching blueprint. Not
    expected in normal operation — Module 5 never validates a
    solution_public_id that didn't come from Module 4 in the first
    place — but checked rather than assumed, since Module 6 has no
    direct read access to confirm the two modules stayed in sync.
    """


class BusinessBlueprintVersionNotFoundError(Exception):
    """Raised when a requested BusinessBlueprintVersion does not exist
    for the given solution_public_id."""


class SectionGenerationError(Exception):
    """
    Raised when a bounded generation group (generator.py, Build Order
    Step 5) fails to produce usable output for its sections — malformed
    JSON, missing required sections within the group, etc. Mirrors
    Module 4's "a bad model response should not crash the run, but
    should not be silently coerced into looking valid either" principle;
    report.py's orchestrator decides how this interacts with persisting
    a partial BusinessBlueprintVersion.
    """
