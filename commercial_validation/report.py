"""
phoenix/commercial_validation/report.py — orchestrator.

validate_solutions() is the single entry point, Module 5's equivalent
of solution_generation/report.py::generate_solutions(). Pulls every
active blueprint for one opportunity (fetch_blueprints), validates each
one INDEPENDENTLY (Comparative Validation Rule — no cross-blueprint
reasoning inside validator.py's prompt), then performs the comparative
pass HERE, in the orchestrator only, persists a new ValidationVersion
(deactivating any prior active version for this
solution_generation_version_id), and returns the assembled result.

Future-Proofing Rule: additional deterministic scoring contributors
(SEO metrics, pricing APIs, search volume, competition intelligence,
trend analysis — spec §20) plug in here as additional calls alongside
validate_blueprint(), contributing to the same accepted-results list
before persistence — this is the seam, not validator.py's signature or
the public ValidationVersion/get_active_validations() output contract.

Generation-version resolution note: rather than re-deriving
scoring_version_id (which isn't part of get_active_solutions()'s return
shape, and adding it would mean touching Module 4 a second time), this
resolves the target SolutionGenerationVersion by
(cluster_id, generation_version) — generation_version comes straight
from fetch_blueprints()'s already-correct resolution (which internally
used Module 4's own scoring_version resolution logic). Precise, and
doesn't require reopening a module that's now frozen.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from phoenix.db import get_session
from phoenix.solution_generation.models import SolutionGenerationVersion
from phoenix.commercial_validation.models import ValidationVersion, ValidatedSolutionBlueprint
from phoenix.commercial_validation.fetch_blueprints import get_blueprint_set
from phoenix.commercial_validation.validator import (
    validate_blueprint,
    PROMPT_VERSION,
    TEMPERATURE,
    DEFAULT_MODEL,
    SCORE_FIELDS,
)
from phoenix.commercial_validation.validate import validate_results
from phoenix.commercial_validation.audit import compute_validation_hash
from phoenix.commercial_validation.exceptions import (
    BlueprintSetNotFoundError,
    ValidationVersionNotFoundError,
)

from shared_services.registry import get_model_service, get_logging_service

MODULE_VERSION = "phoenix-module5-v1"


def _log(event_type: str, cluster_id: int, message: str, severity: str = "info") -> None:
    """Same detail=dict[str, Any] contract as scoring/report.py::_log
    and solution_generation/report.py::_log."""
    try:
        logging_service = get_logging_service()
        logging_service.log_event(
            source="phoenix",
            event_type=event_type,
            detail={"message": message},
            component="commercial_validation",
            severity=severity,
            correlation_id=str(cluster_id),
        )
    except Exception:
        # Logging must never break a validation run.
        pass


def _insufficient_evidence_result(run_id: int, cluster_id: int, reason: str) -> Dict[str, Any]:
    """Same §15/16-style shape as Module 4's Insufficient Commercial
    Evidence result."""
    return {
        "run_id": run_id,
        "cluster_id": cluster_id,
        "status": "Insufficient Commercial Evidence",
        "explanation": reason,
        "validated_blueprints": [],
    }


def _overall_score(result: Dict[str, Any]) -> float:
    """
    Unweighted mean of the nine §8 category scores. Flagged assumption
    (see models.py docstring) — spec supplies no explicit weights,
    unlike Module 3's scoring. This is the one place to change the
    formula if Carl later supplies real weights; nothing else in this
    file or models.py needs to change.
    """
    return sum(result[f] for f in SCORE_FIELDS) / len(SCORE_FIELDS)


def _comparative_summary(scored: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Spec §9: compare all validated solutions belonging to the same
    Opportunity, explainably. Deterministic — sorts by
    overall_validation_score, no AI call — so this can never violate
    the Comparative Validation Rule (comparison happens only here, in
    the orchestrator, never inside validator.py's prompt).
    """
    if not scored:
        return {}
    ranked = sorted(scored, key=lambda r: r["overall_validation_score"], reverse=True)
    top = ranked[0]
    return {
        "strongest_candidate": top["solution_public_id"],
        "strongest_candidate_score": top["overall_validation_score"],
        "ranking": [
            {
                "solution_public_id": r["solution_public_id"],
                "overall_validation_score": r["overall_validation_score"],
            }
            for r in ranked
        ],
    }


def validate_solutions(
    run_id: int,
    cluster_id: int,
    scoring_version: Optional[int] = None,
    model_used: Optional[str] = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    Validate every active SolutionBlueprint for one opportunity.

    Returns either an "Insufficient Commercial Evidence" result (no
    blueprints exist yet, or none survived the AI call + Validation
    Output Validation), or the assembled result: persisted
    ValidationVersion + ValidatedSolutionBlueprint rows, the audit
    block, and the comparative summary.
    """
    try:
        blueprint_set = get_blueprint_set(run_id, cluster_id, scoring_version)
    except BlueprintSetNotFoundError as exc:
        return _insufficient_evidence_result(run_id, cluster_id, str(exc))

    blueprints = blueprint_set["blueprints"]
    problem_statement = blueprint_set.get("problem_statement", "")
    supporting_evidence_refs = blueprint_set.get("supporting_evidence_refs", [])
    generation_version_number = blueprint_set["generation_version"]

    model_service = get_model_service()

    raw_results: List[Dict[str, Any]] = []
    for bp in blueprints:
        try:
            result = validate_blueprint(
                model_service, bp, problem_statement, supporting_evidence_refs, model=model_used
            )
        except ValueError as exc:
            _log(
                "solution_validation_call_failed",
                cluster_id,
                f"blueprint {bp.get('public_id')}: {exc}",
                severity="warning",
            )
            continue
        result["solution_public_id"] = bp["public_id"]
        raw_results.append(result)

    accepted, rejected = validate_results(raw_results)

    if rejected:
        _log(
            "solution_validation_results_rejected",
            cluster_id,
            f"{len(rejected)} validation result(s) failed Validation Output Validation",
            severity="warning",
        )

    if not accepted:
        return _insufficient_evidence_result(
            run_id,
            cluster_id,
            f"No blueprint validation produced usable output — 0 of "
            f"{len(blueprints)} candidate(s) survived the AI call and Validation Output Validation.",
        )

    for r in accepted:
        r["overall_validation_score"] = _overall_score(r)

    comparative_summary = _comparative_summary(accepted)

    with get_session() as session:
        generation_version_row = (
            session.query(SolutionGenerationVersion)
            .filter(
                SolutionGenerationVersion.cluster_id == cluster_id,
                SolutionGenerationVersion.generation_version == generation_version_number,
            )
            .first()
        )
        if generation_version_row is None:
            raise ValidationVersionNotFoundError(
                f"SolutionGenerationVersion (cluster={cluster_id}, "
                f"generation_version={generation_version_number}) not found during validation persistence"
            )

        prior_active = (
            session.query(ValidationVersion)
            .filter(
                ValidationVersion.solution_generation_version_id == generation_version_row.id,
                ValidationVersion.is_active.is_(True),
            )
            .first()
        )
        next_version_number = (
            session.query(ValidationVersion)
            .filter(ValidationVersion.solution_generation_version_id == generation_version_row.id)
            .count()
            + 1
        )
        if prior_active:
            prior_active.is_active = False

        validated_at = dt.datetime.now(dt.timezone.utc).isoformat()
        report_body_for_hash = {
            "run_id": run_id,
            "cluster_id": cluster_id,
            "validation_version": next_version_number,
            "validated_at": validated_at,
            "module_version": MODULE_VERSION,
            "results": accepted,
        }
        validation_hash = compute_validation_hash(
            input_blueprint_ids=[r["solution_public_id"] for r in accepted],
            prompt_version=PROMPT_VERSION,
            model_version=model_used or "default",
            report_without_hash=report_body_for_hash,
        )

        validation_version_row = ValidationVersion(
            solution_generation_version_id=generation_version_row.id,
            validation_version=next_version_number,
            is_active=True,
            module_version=MODULE_VERSION,
            prompt_version=PROMPT_VERSION,
            model_used=model_used or "default",
            temperature=TEMPERATURE,
            hash=validation_hash,
            comparative_summary=comparative_summary,
        )
        session.add(validation_version_row)
        session.flush()  # populate validation_version_row.id

        validated_rows: List[ValidatedSolutionBlueprint] = []
        for r in accepted:
            row = ValidatedSolutionBlueprint(
                validation_version_id=validation_version_row.id,
                solution_public_id=r["solution_public_id"],
                market_need_score=r["market_need_score"],
                customer_pain_score=r["customer_pain_score"],
                revenue_potential_score=r["revenue_potential_score"],
                competition_score=r["competition_score"],
                technical_complexity_score=r["technical_complexity_score"],
                time_to_mvp_score=r["time_to_mvp_score"],
                founder_fit_score=r["founder_fit_score"],
                ai_leverage_score=r["ai_leverage_score"],
                defensibility_score=r["defensibility_score"],
                overall_validation_score=r["overall_validation_score"],
                overall_recommendation=r["overall_recommendation"],
                validation_confidence=r["validation_confidence"],
                validation_explanation=r["validation_explanation"],
                strengths=r["strengths"],
                weaknesses=r["weaknesses"],
                primary_risks=r["primary_risks"],
                suggested_improvements=r["suggested_improvements"],
            )
            session.add(row)
            validated_rows.append(row)
        session.flush()  # populate id on each validated blueprint row

        _log(
            "solution_validation_completed",
            cluster_id,
            f"validated {len(validated_rows)} blueprint(s), version {next_version_number}",
        )

        return {
            "run_id": run_id,
            "cluster_id": cluster_id,
            "generation_version": generation_version_number,
            "validation_version": next_version_number,
            "status": "Validated",
            "candidates_validated": len(accepted),
            "candidates_rejected": len(rejected),
            "comparative_summary": comparative_summary,
            "validated_blueprints": [_serialize(v) for v in validated_rows],
            "audit": {
                "module_version": MODULE_VERSION,
                "prompt_version": PROMPT_VERSION,
                "model_used": model_used or "default",
                "temperature": TEMPERATURE,
                "validation_version": next_version_number,
                "timestamp": validated_at,
                "hash": validation_hash,
            },
        }


def _serialize(v: ValidatedSolutionBlueprint) -> Dict[str, Any]:
    """Shared row -> dict shape, used by both validate_solutions() and
    get_active_validations() so the two return payloads never drift."""
    return {
        "solution_public_id": v.solution_public_id,
        "market_need_score": v.market_need_score,
        "customer_pain_score": v.customer_pain_score,
        "revenue_potential_score": v.revenue_potential_score,
        "competition_score": v.competition_score,
        "technical_complexity_score": v.technical_complexity_score,
        "time_to_mvp_score": v.time_to_mvp_score,
        "founder_fit_score": v.founder_fit_score,
        "ai_leverage_score": v.ai_leverage_score,
        "defensibility_score": v.defensibility_score,
        "overall_validation_score": v.overall_validation_score,
        "overall_recommendation": v.overall_recommendation,
        "validation_confidence": v.validation_confidence,
        "validation_explanation": v.validation_explanation,
        "strengths": v.strengths,
        "weaknesses": v.weaknesses,
        "primary_risks": v.primary_risks,
        "suggested_improvements": v.suggested_improvements,
    }


def get_active_validations(run_id: int, cluster_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch the currently active ValidationVersion's results for one
    opportunity, or None if nothing has been validated yet. Same
    "don't trigger an expensive re-validation on every page load"
    reasoning as Module 4's get_active_solutions().

    Resolves the most recent SolutionGenerationVersion for this
    cluster_id — same simplification flagged in module docstring:
    correct for the normal one-active-generation-per-cluster case; if a
    cluster ever has multiple distinct ScoringVersions each with their
    own active generation, this takes the newest generation_version by
    number, not necessarily one tied to a specific scoring_version.
    Flag to Carl if that scenario is ever real; not a Module 4 contract
    issue, a Module 5 lookup simplification.
    """
    with get_session() as session:
        generation_version_row = (
            session.query(SolutionGenerationVersion)
            .filter(SolutionGenerationVersion.cluster_id == cluster_id)
            .order_by(SolutionGenerationVersion.generation_version.desc())
            .first()
        )
        if generation_version_row is None:
            return None

        active_version = (
            session.query(ValidationVersion)
            .filter(
                ValidationVersion.solution_generation_version_id == generation_version_row.id,
                ValidationVersion.is_active.is_(True),
            )
            .first()
        )
        if active_version is None:
            return None

        rows = (
            session.query(ValidatedSolutionBlueprint)
            .filter(ValidatedSolutionBlueprint.validation_version_id == active_version.id)
            .all()
        )

        return {
            "run_id": run_id,
            "cluster_id": cluster_id,
            "generation_version": generation_version_row.generation_version,
            "validation_version": active_version.validation_version,
            "comparative_summary": active_version.comparative_summary,
            "validated_blueprints": [_serialize(v) for v in rows],
            "audit": {
                "module_version": active_version.module_version,
                "prompt_version": active_version.prompt_version,
                "model_used": active_version.model_used,
                "temperature": active_version.temperature,
                "validation_version": active_version.validation_version,
                "timestamp": active_version.created_at.isoformat(),
                "hash": active_version.hash,
            },
        }


def list_validation_versions(solution_generation_version_id: int) -> List[Dict[str, Any]]:
    """List all validation versions for one SolutionGenerationVersion, newest first."""
    with get_session() as session:
        rows = (
            session.query(ValidationVersion)
            .filter(ValidationVersion.solution_generation_version_id == solution_generation_version_id)
            .order_by(ValidationVersion.validation_version.desc())
            .all()
        )
        return [
            {
                "validation_version": r.validation_version,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat(),
                "model_used": r.model_used,
                "hash": r.hash,
            }
            for r in rows
        ]


def list_validation_versions_for_opportunity(run_id: int, cluster_id: int) -> List[Dict[str, Any]]:
    """
    Same (run_id, cluster_id) convenience as Module 4's own
    list_generation_versions_for_opportunity() — resolves the relevant
    SolutionGenerationVersion internally (same lookup-simplification
    flagged on get_active_validations()), then delegates to
    list_validation_versions(). run_id isn't used in the lookup itself
    (SolutionGenerationVersion has no run_id column, only cluster_id),
    but kept in the signature for symmetry with every other Module 5
    function and because the caller always has it in scope anyway.
    """
    with get_session() as session:
        generation_version_row = (
            session.query(SolutionGenerationVersion)
            .filter(SolutionGenerationVersion.cluster_id == cluster_id)
            .order_by(SolutionGenerationVersion.generation_version.desc())
            .first()
        )
        if generation_version_row is None:
            return []
        solution_generation_version_id = generation_version_row.id

    return list_validation_versions(solution_generation_version_id)
