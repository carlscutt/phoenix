"""
phoenix/business_blueprint/fetch_validated_blueprint.py

Module 6's single read layer into Modules 4 and 5 — the concrete
implementation of Decision 2 (approved with the Build Order): Module 6
consumes public report interfaces from Modules 3-5 only, never direct
database tables or internal classes.

Calls exactly two functions, both already public, both already used by
other modules for the same purpose:

  - phoenix.commercial_validation.report.get_active_validations() —
    same function Module 5's own Studio UI results view reads from.
    Gives Module 6 the validated blueprint's scores, recommendation,
    confidence, strengths/weaknesses/risks/improvements, and the
    comparative summary.

  - phoenix.solution_generation.report.get_active_solutions() — same
    function Module 5's fetch_blueprints.py already calls to read
    Module 4. Gives Module 6 the actual business concept content
    (working_title, solution_type, revenue_model, etc.) and the
    opportunity-level problem_statement/supporting_evidence_refs —
    none of which exist on Module 5's own tables (ValidatedSolutionBlueprint
    stores solution_public_id as a plain string, confirmed against the
    real commercial_validation/models.py — no cross-DB FK, no embedded
    blueprint content).

Never calls validate_solutions() or generate_solutions() — read-only
against both modules throughout, same "never trigger upstream
generation as a side effect of a read" discipline fetch_blueprints.py
established for Module 5 reading Module 4.

solution_public_id is the explicit selection parameter (Decision 3) —
this file does not infer, rank, or pick a blueprint on the caller's
behalf. Module 5's get_active_validations() returns every validated
blueprint for the opportunity (it's a comparative pass across the whole
set); this file's job is narrowing that down to the one the caller
asked for, by solution_public_id, and pairing it with its Module 4
content.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from phoenix.commercial_validation.report import get_active_validations
from phoenix.solution_generation.report import get_active_solutions
from phoenix.business_blueprint.exceptions import (
    ValidatedBlueprintNotFoundError,
    SolutionNotFoundError,
)


def get_validated_blueprint(
    run_id: int,
    cluster_id: int,
    solution_public_id: str,
) -> Dict[str, Any]:
    """
    Fetch everything Module 6 needs to generate a Business Blueprint for
    one specific validated solution.

    Returns:
        {
            "run_id": run_id,
            "cluster_id": cluster_id,
            "solution_public_id": solution_public_id,
            "generation_version": <Module 4's generation_version number>,
            "validation_version": <Module 5's validation_version number>,
            "problem_statement": <opportunity-level, from Module 4>,
            "supporting_evidence_refs": <opportunity-level, from Module 4>,
            "solution_blueprint": <the one matching blueprint dict from
                get_active_solutions()'s "blueprints" list — working_title,
                solution_type, target_customer, customer_problem,
                value_proposition, commercial_patterns, revenue_model,
                delivery_model, pricing_strategy, automation_potential,
                estimated_build_complexity, estimated_time_to_mvp,
                required_skills, primary_risks, key_assumptions,
                confidence, reasoning>,
            "validated_blueprint": <the one matching validated dict from
                get_active_validations()'s "validated_blueprints" list —
                the 9 SCORE_FIELDS, overall_validation_score,
                overall_recommendation, validation_confidence,
                validation_explanation, strengths, weaknesses,
                primary_risks, suggested_improvements>,
            "comparative_summary": <Module 5's ranking across the whole
                validated set, for context — strongest_candidate may or
                may not be this solution_public_id>,
            "solution_audit": <Module 4's audit block>,
            "validation_audit": <Module 5's audit block — no
                correlation_id field, confirmed against the real
                ValidationVersion schema; Module 6's own audit.py mints
                its own rather than inheriting one, since there is
                nothing real to inherit>,
        }

    Raises:
        ValidatedBlueprintNotFoundError: no active validation exists for
            this opportunity, or one exists but has no entry matching
            solution_public_id. Tells the caller to run Module 5
            (Validate Solutions) first, or check the id.
        SolutionNotFoundError: Module 5 has a validated result for
            solution_public_id, but Module 4's own get_active_solutions()
            no longer has a matching blueprint. Not expected in normal
            operation (Module 5 never validates a solution_public_id
            Module 4 didn't produce) — checked rather than assumed.
    """
    validation = get_active_validations(run_id, cluster_id)
    if validation is None:
        raise ValidatedBlueprintNotFoundError(
            f"No active validation found for run_id={run_id}, cluster_id={cluster_id}. "
            f"Run Module 5 (Validate Solutions) before generating a Business Blueprint."
        )

    validated_blueprint = next(
        (
            vb
            for vb in validation["validated_blueprints"]
            if vb["solution_public_id"] == solution_public_id
        ),
        None,
    )
    if validated_blueprint is None:
        raise ValidatedBlueprintNotFoundError(
            f"No validated blueprint with solution_public_id={solution_public_id!r} "
            f"found under run_id={run_id}, cluster_id={cluster_id}'s active validation."
        )

    solutions = get_active_solutions(run_id, cluster_id)
    if solutions is None:
        # Shouldn't happen — a validation can't exist without blueprints
        # having existed to validate — but checked, not assumed, same
        # discipline as every other cross-module read in this project.
        raise SolutionNotFoundError(
            f"Module 5 has a validated result for solution_public_id="
            f"{solution_public_id!r}, but Module 4's get_active_solutions() "
            f"returned nothing for run_id={run_id}, cluster_id={cluster_id}."
        )

    solution_blueprint = next(
        (b for b in solutions["blueprints"] if b["public_id"] == solution_public_id),
        None,
    )
    if solution_blueprint is None:
        raise SolutionNotFoundError(
            f"Module 5 has a validated result for solution_public_id="
            f"{solution_public_id!r}, but no matching blueprint was found in "
            f"Module 4's active get_active_solutions() result for "
            f"run_id={run_id}, cluster_id={cluster_id}."
        )

    return {
        "run_id": run_id,
        "cluster_id": cluster_id,
        "solution_public_id": solution_public_id,
        "generation_version": solutions["generation_version"],
        "validation_version": validation["validation_version"],
        "problem_statement": solutions.get("problem_statement", ""),
        "supporting_evidence_refs": solutions.get("supporting_evidence_refs", []),
        "solution_blueprint": solution_blueprint,
        "validated_blueprint": validated_blueprint,
        "comparative_summary": validation.get("comparative_summary", {}),
        "solution_audit": solutions.get("audit", {}),
        "validation_audit": validation.get("audit", {}),
    }
