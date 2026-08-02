"""
phoenix/commercial_validation/fetch_blueprints.py

Fetches the full active SolutionBlueprint set for one opportunity via
the extended Module 4 contract (report.py Step 0: problem_statement,
supporting_evidence_refs, and audit are now all present on
get_active_solutions()'s return).

Deliberately does NOT fall back to calling generate_solutions() if
nothing exists yet — Module 5 never generates blueprints itself (spec
§3 "It does not generate new ideas", §21 explicit non-goals). If
nothing has been generated, the caller (report.py) is told to send the
person back to Module 4 first, same as the existing Studio flow already
requires Score → Generate Solution Blueprints → (now) Validate, in
that order.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from phoenix.solution_generation.report import get_active_solutions
from phoenix.commercial_validation.exceptions import BlueprintSetNotFoundError


def get_blueprint_set(
    run_id: int,
    cluster_id: int,
    scoring_version: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Returns the dict shape produced by get_active_solutions(): run_id,
    cluster_id, generation_version, problem_statement,
    supporting_evidence_refs, blueprints, audit.

    Raises BlueprintSetNotFoundError if nothing has ever been generated
    for this opportunity, or if the active generation has zero
    blueprints (shouldn't happen given Module 4's own MIN_SOLUTIONS
    floor, but checked rather than assumed).
    """
    result = get_active_solutions(run_id, cluster_id, scoring_version=scoring_version)
    if result is None:
        raise BlueprintSetNotFoundError(
            f"No solution blueprints found for run_id={run_id}, cluster_id={cluster_id}. "
            f"Generate Solution Blueprints (Module 4) before validating."
        )
    if not result.get("blueprints"):
        raise BlueprintSetNotFoundError(
            f"Blueprint set for run_id={run_id}, cluster_id={cluster_id} is empty."
        )
    return result
