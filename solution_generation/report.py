"""
Module 4 (Solution Generation Engine) — orchestrator.

generate_solutions() is the single entry point, the Module 4 equivalent
of phoenix/scoring/report.py::score_run(). Pulls the one selected
OpportunityScoreEntry, runs generation + validation, persists a new
SolutionGenerationVersion (deactivating any prior active version for
this opportunity), and returns the assembled result.

Follows the same conventions as phoenix/scoring/report.py throughout:
get_session()'s auto-commit-on-clean-exit (no manual session.commit()),
LoggingService's detail=dict[str, Any] contract, get_model_service()/
get_logging_service() via the registry, prior-active-deactivation before
persisting the new version.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from phoenix.db import get_session
from phoenix.scoring.exceptions import ScoringVersionNotFoundError
from phoenix.solution_generation.models import SolutionGenerationVersion, SolutionBlueprint
from phoenix.solution_generation.fetch_entry import get_opportunity_entry
from phoenix.solution_generation.generator import generate_candidates, PROMPT_VERSION, TEMPERATURE, DEFAULT_MODEL
from phoenix.solution_generation.validate import validate_candidates
from phoenix.solution_generation.audit import compute_generation_hash
from phoenix.solution_generation.exceptions import (
    OpportunityEntryNotFoundError,
    SolutionGenerationVersionNotFoundError,
    BlueprintNotFoundError,
)

from shared_services.registry import get_model_service, get_logging_service

MODULE_VERSION = "phoenix-module4-v1"
MIN_SOLUTIONS = 3  # spec §12 diversity floor; §15 allows returning 2 if that's genuinely all the evidence supports


def _log(event_type: str, cluster_id: int, message: str, severity: str = "info") -> None:
    """Same detail=dict[str, Any] contract as scoring/report.py::_log."""
    try:
        logging_service = get_logging_service()
        logging_service.log_event(
            source="phoenix",
            event_type=event_type,
            detail={"message": message},
            component="solution_generation",
            severity=severity,
            correlation_id=str(cluster_id),
        )
    except Exception:
        # Logging must never break a generation run.
        pass


def _insufficient_evidence_result(
    run_id: int,
    cluster_id: int,
    reason: str,
    candidates_generated: int = 0,
    candidates_rejected: int = 0,
) -> Dict[str, Any]:
    """Spec §15: Insufficient Commercial Evidence, with explanation."""
    return {
        "run_id": run_id,
        "cluster_id": cluster_id,
        "status": "Insufficient Commercial Evidence",
        "explanation": reason,
        "blueprints": [],
        "candidates_generated": candidates_generated,
        "candidates_rejected": candidates_rejected,
    }


def generate_solutions(
    run_id: int,
    cluster_id: int,
    scoring_version: Optional[int] = None,
    model_used: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    Generate SolutionBlueprints for a single selected opportunity.

    Returns either:
      - a §15 "Insufficient Commercial Evidence" result (no AI call made,
        or too few candidates survived validation), or
      - the assembled result: persisted SolutionGenerationVersion +
        SolutionBlueprint rows, plus the audit block.
    """
    try:
        fetched = get_opportunity_entry(run_id, cluster_id, scoring_version)
    except OpportunityEntryNotFoundError as exc:
        return _insufficient_evidence_result(run_id, cluster_id, str(exc))

    entry = fetched["entry"]
    resolved_scoring_version = fetched["scoring_version"]

    if entry["status"] == "Insufficient Evidence":
        _log(
            "solution_generation_skipped",
            cluster_id,
            "source opportunity has Insufficient Evidence status; generation not attempted",
        )
        return _insufficient_evidence_result(
            run_id, cluster_id, "Source opportunity has Insufficient Evidence status."
        )

    model_service = get_model_service()
    candidates = generate_candidates(model_service, entry, model=model_used)
    accepted, rejected = validate_candidates(candidates)

    if rejected:
        _log(
            "solution_generation_candidates_rejected",
            cluster_id,
            f"{len(rejected)} candidate(s) failed Blueprint Validation",
            severity="warning",
        )

    if len(accepted) < MIN_SOLUTIONS:
        # §15: if only two viable solutions genuinely exist, accept two —
        # but if validation left FEWER than that (0 or 1), that's
        # insufficient, not a diversity shortfall to pad around.
        if len(accepted) < 2:
            _log(
                "solution_generation_insufficient",
                cluster_id,
                f"only {len(accepted)} candidate(s) survived validation",
                severity="warning",
            )
            return _insufficient_evidence_result(
                run_id,
                cluster_id,
                f"Only {len(accepted)} valid solution candidate(s) survived generation "
                f"and validation — below the minimum needed for a useful comparison.",
                candidates_generated=len(candidates),
                candidates_rejected=len(rejected),
            )

    with get_session() as session:
        from phoenix.scoring.models import ScoringVersion  # local import: only needed for the FK lookup below

        scoring_version_row = (
            session.query(ScoringVersion)
            .filter(
                ScoringVersion.phoenix_run_id == run_id,
                ScoringVersion.scoring_version == resolved_scoring_version,
            )
            .first()
        )
        if scoring_version_row is None:
            raise ScoringVersionNotFoundError(
                f"ScoringVersion {resolved_scoring_version} for run {run_id} not found "
                f"during solution generation persistence"
            )

        prior_active = (
            session.query(SolutionGenerationVersion)
            .filter(
                SolutionGenerationVersion.scoring_version_id == scoring_version_row.id,
                SolutionGenerationVersion.cluster_id == cluster_id,
                SolutionGenerationVersion.is_active.is_(True),
            )
            .first()
        )
        next_version_number = (
            session.query(SolutionGenerationVersion)
            .filter(
                SolutionGenerationVersion.scoring_version_id == scoring_version_row.id,
                SolutionGenerationVersion.cluster_id == cluster_id,
            )
            .count()
            + 1
        )
        if prior_active:
            prior_active.is_active = False

        generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
        report_body_for_hash = {
            "run_id": run_id,
            "cluster_id": cluster_id,
            "generation_version": next_version_number,
            "generated_at": generated_at,
            "module_version": MODULE_VERSION,
            "blueprints": accepted,
        }
        generation_hash = compute_generation_hash(
            input_evidence=[entry.get("supporting_evidence_refs", [])],
            prompt_version=PROMPT_VERSION,
            model_version=model_used,
            report_without_hash=report_body_for_hash,
        )

        generation_version_row = SolutionGenerationVersion(
            scoring_version_id=scoring_version_row.id,
            cluster_id=cluster_id,
            generation_version=next_version_number,
            is_active=True,
            module_version=MODULE_VERSION,
            prompt_version=PROMPT_VERSION,
            model_used=model_used,
            temperature=TEMPERATURE,
            hash=generation_hash,
        )
        session.add(generation_version_row)
        session.flush()  # populate generation_version_row.id

        blueprint_rows: List[SolutionBlueprint] = []
        for c in accepted:
            row = SolutionBlueprint(
                solution_generation_version_id=generation_version_row.id,
                working_title=c["working_title"],
                solution_type=c["solution_type"],
                estimated_customer_type=c["estimated_customer_type"],
                target_customer=c["target_customer"],
                customer_problem=c["customer_problem"],
                value_proposition=c["value_proposition"],
                commercial_patterns=c["commercial_patterns"],
                revenue_model=c["revenue_model"],
                delivery_model=c["delivery_model"],
                pricing_strategy=c["pricing_strategy"],
                automation_potential=c["automation_potential"],
                estimated_build_complexity=c["estimated_build_complexity"],
                estimated_time_to_mvp=c["estimated_time_to_mvp"],
                required_skills=c["required_skills"],
                primary_risks=c["primary_risks"],
                key_assumptions=c["key_assumptions"],
                confidence=c["confidence"],
                reasoning=c["reasoning"],
            )
            session.add(row)
            blueprint_rows.append(row)
        session.flush()  # populate public_id / id on each blueprint row

        _log(
            "solution_generation_completed",
            cluster_id,
            f"generated {len(blueprint_rows)} blueprint(s), version {next_version_number}",
        )

        return {
            "run_id": run_id,
            "cluster_id": cluster_id,
            "scoring_version": resolved_scoring_version,
            "generation_version": next_version_number,
            "status": "Generated",
            "candidates_generated": len(candidates),
            "candidates_rejected": len(rejected),
            "blueprints": [
                {
                    "public_id": b.public_id,
                    "working_title": b.working_title,
                    "solution_type": b.solution_type,
                    "estimated_customer_type": b.estimated_customer_type,
                    "target_customer": b.target_customer,
                    "customer_problem": b.customer_problem,
                    "value_proposition": b.value_proposition,
                    "commercial_patterns": b.commercial_patterns,
                    "revenue_model": b.revenue_model,
                    "delivery_model": b.delivery_model,
                    "pricing_strategy": b.pricing_strategy,
                    "automation_potential": b.automation_potential,
                    "estimated_build_complexity": b.estimated_build_complexity,
                    "estimated_time_to_mvp": b.estimated_time_to_mvp,
                    "required_skills": b.required_skills,
                    "primary_risks": b.primary_risks,
                    "key_assumptions": b.key_assumptions,
                    "confidence": b.confidence,
                    "approved": b.approved,
                    "reasoning": b.reasoning,
                }
                for b in blueprint_rows
            ],
            "audit": {
                "module_version": MODULE_VERSION,
                "prompt_version": PROMPT_VERSION,
                "model_used": model_used,
                "temperature": TEMPERATURE,
                "generation_version": next_version_number,
                "timestamp": generated_at,
                "hash": generation_hash,
            },
        }


def list_solution_generation_versions(scoring_version_id: int, cluster_id: int) -> List[Dict[str, Any]]:
    """List all solution generation versions for one opportunity, newest first."""
    with get_session() as session:
        rows = (
            session.query(SolutionGenerationVersion)
            .filter(
                SolutionGenerationVersion.scoring_version_id == scoring_version_id,
                SolutionGenerationVersion.cluster_id == cluster_id,
            )
            .order_by(SolutionGenerationVersion.generation_version.desc())
            .all()
        )
        return [
            {
                "generation_version": r.generation_version,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat(),
                "model_used": r.model_used,
                "hash": r.hash,
            }
            for r in rows
        ]


def list_generation_versions_for_opportunity(
    run_id: int,
    cluster_id: int,
    scoring_version: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Same (run_id, cluster_id, scoring_version) shape as generate_solutions()
    — resolves the internal scoring_version_id, then delegates to
    list_solution_generation_versions().
    """
    fetched = get_opportunity_entry(run_id, cluster_id, scoring_version)
    with get_session() as session:
        from phoenix.scoring.models import ScoringVersion

        scoring_version_row = (
            session.query(ScoringVersion)
            .filter(
                ScoringVersion.phoenix_run_id == run_id,
                ScoringVersion.scoring_version == fetched["scoring_version"],
            )
            .first()
        )
        if scoring_version_row is None:
            return []
        scoring_version_id = scoring_version_row.id

    return list_solution_generation_versions(scoring_version_id, cluster_id)


def get_active_solutions(
    run_id: int,
    cluster_id: int,
    scoring_version: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Fetch the currently active SolutionGenerationVersion's blueprints for
    one opportunity, or None if nothing has been generated for it yet.
    Used by the Studio UI to show existing blueprints without triggering
    a new (expensive, real-Ollama-call) generation on every page load.
    """
    fetched = get_opportunity_entry(run_id, cluster_id, scoring_version)

    with get_session() as session:
        from phoenix.scoring.models import ScoringVersion

        scoring_version_row = (
            session.query(ScoringVersion)
            .filter(
                ScoringVersion.phoenix_run_id == run_id,
                ScoringVersion.scoring_version == fetched["scoring_version"],
            )
            .first()
        )
        if scoring_version_row is None:
            return None

        active_version = (
            session.query(SolutionGenerationVersion)
            .filter(
                SolutionGenerationVersion.scoring_version_id == scoring_version_row.id,
                SolutionGenerationVersion.cluster_id == cluster_id,
                SolutionGenerationVersion.is_active.is_(True),
            )
            .first()
        )
        if active_version is None:
            return None

        blueprint_rows = (
            session.query(SolutionBlueprint)
            .filter(SolutionBlueprint.solution_generation_version_id == active_version.id)
            .all()
        )

        return {
            "generation_version": active_version.generation_version,
            "blueprints": [
                {
                    "public_id": b.public_id,
                    "working_title": b.working_title,
                    "solution_type": b.solution_type,
                    "estimated_customer_type": b.estimated_customer_type,
                    "target_customer": b.target_customer,
                    "customer_problem": b.customer_problem,
                    "value_proposition": b.value_proposition,
                    "commercial_patterns": b.commercial_patterns,
                    "revenue_model": b.revenue_model,
                    "delivery_model": b.delivery_model,
                    "pricing_strategy": b.pricing_strategy,
                    "automation_potential": b.automation_potential,
                    "estimated_build_complexity": b.estimated_build_complexity,
                    "estimated_time_to_mvp": b.estimated_time_to_mvp,
                    "required_skills": b.required_skills,
                    "primary_risks": b.primary_risks,
                    "key_assumptions": b.key_assumptions,
                    "confidence": b.confidence,
                    "approved": b.approved,
                    "reasoning": b.reasoning,
                }
                for b in blueprint_rows
            ],
        }


def approve_blueprint(public_id: str, approved: bool = True) -> Dict[str, Any]:
    """
    Set the Approve Solution flag on one blueprint (spec §17). Approving
    one blueprint has no effect on its siblings in the same
    SolutionGenerationVersion — approval is per-blueprint, not per-run,
    since the whole point of generating several is to let the person
    pick the ones worth pursuing, not to accept or reject the batch as
    a whole.

    Raises BlueprintNotFoundError if public_id doesn't match any
    persisted SolutionBlueprint.
    """
    with get_session() as session:
        row = (
            session.query(SolutionBlueprint)
            .filter(SolutionBlueprint.public_id == public_id)
            .first()
        )
        if row is None:
            raise BlueprintNotFoundError(f"No SolutionBlueprint with public_id={public_id!r}")

        row.approved = approved
        session.flush()

        return {
            "public_id": row.public_id,
            "working_title": row.working_title,
            "approved": row.approved,
        }
