"""
phoenix/business_blueprint/report.py

Module 6 (Business Blueprint Engine) orchestrator. Ties Steps 1-7
together into three public functions:

  generate_business_blueprint(run_id, cluster_id, solution_public_id, model)
      Runs all six bounded generation groups (categories.BATCH_GROUPS),
      validates each and the assembled whole (validate.py), computes
      the audit hash (audit.py), and persists a new
      BusinessBlueprintVersion + its BusinessBlueprintSection rows
      (models.py), deactivating any prior active version for this
      solution_public_id — same versioning contract as every other
      module (SolutionGenerationVersion.generation_version,
      ValidationVersion.validation_version).

  get_active_blueprint(solution_public_id)
      Read-only. Returns the currently active Business Blueprint for a
      solution_public_id, or None if none exists yet — same "None if
      nothing active" contract as get_active_solutions() and
      get_active_validations().

  list_blueprint_versions(solution_public_id)
      Read-only. Every version ever generated for this solution_public_id,
      newest last.

Logging pattern (_log helper, correlation_id=str(cluster_id), wrapped
in try/except so logging never breaks a run) copied directly from the
confirmed real solution_generation/report.py and commercial_validation/
report.py — not re-derived. Both of those modules' own version tables
have NO correlation_id column at all; they only ever use
correlation_id=str(cluster_id) as a per-log-call parameter. Module 6's
BusinessBlueprintVersion.correlation_id column (added at Step 1) is
populated with that same str(cluster_id) value for consistency and so
the Studio UI can display it — not a separately "inherited" value, since
spec §14's premise (something real to inherit from Module 5) doesn't
exist (confirmed: ValidationVersion's real schema has no correlation_id
field at all).

Versioning/deactivation pattern (next_version_number via count()+1,
prior_active.is_active = False as a direct attribute assignment inside
the same session, rather than a bulk .update() call) also copied
directly from the confirmed real code in both modules — this way, if
final validation fails after the count/deactivate but before commit,
get_session()'s own rollback-on-exception (phoenix/db.py) undoes the
deactivation too, atomically, for free. No separate "read version
number first, validate second, write third" multi-session dance needed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from phoenix.db import get_session
from phoenix.business_blueprint import categories, generator, validate
from phoenix.business_blueprint.audit import compute_business_blueprint_hash
from phoenix.business_blueprint.fetch_validated_blueprint import get_validated_blueprint
from phoenix.business_blueprint.models import BusinessBlueprintVersion, BusinessBlueprintSection
from phoenix.business_blueprint.exceptions import SectionGenerationError

from shared_services.registry import get_model_service, get_logging_service

MODULE_VERSION = "phoenix-module6-v1"


def _log(event_type: str, cluster_id: int, message: str, severity: str = "info") -> None:
    """Same detail=dict[str, Any] contract as scoring/report.py::_log,
    solution_generation/report.py::_log, commercial_validation/report.py::_log."""
    try:
        logging_service = get_logging_service()
        logging_service.log_event(
            source="phoenix",
            event_type=event_type,
            detail={"message": message},
            component="business_blueprint",
            severity=severity,
            correlation_id=str(cluster_id),
        )
    except Exception:
        # Logging must never break a generation run.
        pass


def generate_business_blueprint(
    run_id: int,
    cluster_id: int,
    solution_public_id: str,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates a complete Business Blueprint for one validated solution.

    Raises (propagated, not caught — these are precondition violations,
    not an "insufficient evidence" ambient outcome the way Module 4/5's
    core generation logic has one; the caller is expected to only offer
    this action for a solution_public_id that's already been validated):
        ValidatedBlueprintNotFoundError, SolutionNotFoundError: from
            get_validated_blueprint() (Steps 3-4) if Module 5 hasn't
            validated this opportunity yet, or solution_public_id
            doesn't match anything.
        SectionGenerationError: if any group's generation fails
            (malformed model response) or fails Business Blueprint
            Validation (missing/empty sections, missing reasoning), or
            if the final assembled document fails validation. Nothing
            is persisted if this is raised — the prior active version
            (if any) remains active, since get_session()'s
            rollback-on-exception undoes any in-progress deactivation.

    Returns:
        {
            "status": "Generated",
            "run_id": run_id,
            "cluster_id": cluster_id,
            "solution_public_id": solution_public_id,
            "blueprint_version": <int, this solution's Nth blueprint>,
            "sections": {section_name: {content, reasoning}, ...},  # all 17
            "audit": {module_version, prompt_version, model_version,
                      temperature, audit_hash},
        }
    """
    resolved_model = model or generator.DEFAULT_MODEL

    _log(
        "business_blueprint_generation_started",
        cluster_id,
        f"Generating Business Blueprint for solution_public_id={solution_public_id}",
    )

    fetched = get_validated_blueprint(run_id, cluster_id, solution_public_id)
    model_service = get_model_service()

    group_results: Dict[str, Dict[str, Any]] = {}
    for group in categories.BATCH_GROUPS:
        group_key = group["group"]
        try:
            raw = generator.generate_group(model_service, group_key, fetched, model=resolved_model)
        except SectionGenerationError:
            _log(
                "business_blueprint_group_generation_failed",
                cluster_id,
                f"Group {group_key} generation failed for solution_public_id={solution_public_id}",
                severity="error",
            )
            raise

        is_valid, errors = validate.validate_group_sections(group_key, raw)
        if not is_valid:
            _log(
                "business_blueprint_group_validation_failed",
                cluster_id,
                f"Group {group_key} failed Business Blueprint Validation: {errors}",
                severity="error",
            )
            raise SectionGenerationError(
                f"Group {group_key} failed Business Blueprint Validation: {errors}"
            )

        group_results[group_key] = raw

    merged_sections = validate.merge_section_results(group_results)

    with get_session() as session:
        prior_active = (
            session.query(BusinessBlueprintVersion)
            .filter(
                BusinessBlueprintVersion.solution_public_id == solution_public_id,
                BusinessBlueprintVersion.is_active.is_(True),
            )
            .first()
        )
        next_version_number = (
            session.query(BusinessBlueprintVersion)
            .filter(BusinessBlueprintVersion.solution_public_id == solution_public_id)
            .count()
            + 1
        )

        report_body_for_hash = {
            "run_id": run_id,
            "cluster_id": cluster_id,
            "solution_public_id": solution_public_id,
            "blueprint_version": next_version_number,
            "module_version": MODULE_VERSION,
            "sections": merged_sections,
        }
        audit_hash = compute_business_blueprint_hash(
            solution_public_id=solution_public_id,
            generation_version=fetched["generation_version"],
            validation_version=fetched["validation_version"],
            prompt_version=generator.PROMPT_VERSION,
            model_version=resolved_model,
            report_without_hash=report_body_for_hash,
        )
        audit_block = {
            "module_version": MODULE_VERSION,
            "prompt_version": generator.PROMPT_VERSION,
            "model_version": resolved_model,
            "temperature": generator.TEMPERATURE,
            "audit_hash": audit_hash,
        }

        doc_valid, doc_errors = validate.validate_business_blueprint(merged_sections, audit_block)
        if not doc_valid:
            # Raising here, inside the session and before any write,
            # means get_session()'s rollback-on-exception has nothing
            # to undo yet — prior_active hasn't been touched.
            _log(
                "business_blueprint_final_validation_failed",
                cluster_id,
                f"Assembled Business Blueprint failed final validation: {doc_errors}",
                severity="error",
            )
            raise SectionGenerationError(
                f"Assembled Business Blueprint failed final validation: {doc_errors}"
            )

        if prior_active:
            prior_active.is_active = False

        version_row = BusinessBlueprintVersion(
            solution_public_id=solution_public_id,
            blueprint_version=next_version_number,
            is_active=True,
            correlation_id=str(cluster_id),
            module_version=MODULE_VERSION,
            prompt_version=generator.PROMPT_VERSION,
            model_version=resolved_model,
            temperature=generator.TEMPERATURE,
            audit_hash=audit_hash,
        )
        session.add(version_row)
        session.flush()

        for sort_order, section_name in enumerate(categories.SECTION_NAMES):
            section_data = merged_sections[section_name]
            session.add(
                BusinessBlueprintSection(
                    version_id=version_row.id,
                    section_group=categories.group_for_section(section_name),
                    section_name=section_name,
                    sort_order=sort_order,
                    content=section_data["content"],
                    reasoning=section_data["reasoning"],
                )
            )

        result_version_number = version_row.blueprint_version

    _log(
        "business_blueprint_generated",
        cluster_id,
        f"Business Blueprint v{result_version_number} generated for solution_public_id={solution_public_id}",
    )

    return {
        "status": "Generated",
        "run_id": run_id,
        "cluster_id": cluster_id,
        "solution_public_id": solution_public_id,
        "blueprint_version": result_version_number,
        "sections": merged_sections,
        "audit": audit_block,
    }


def get_active_blueprint(solution_public_id: str) -> Optional[Dict[str, Any]]:
    """Read-only. Returns None if no Business Blueprint has been generated
    yet for this solution_public_id — same contract as
    get_active_solutions()/get_active_validations()."""
    with get_session() as session:
        version_row = (
            session.query(BusinessBlueprintVersion)
            .filter(
                BusinessBlueprintVersion.solution_public_id == solution_public_id,
                BusinessBlueprintVersion.is_active.is_(True),
            )
            .first()
        )
        if version_row is None:
            return None

        section_rows = (
            session.query(BusinessBlueprintSection)
            .filter(BusinessBlueprintSection.version_id == version_row.id)
            .order_by(BusinessBlueprintSection.sort_order)
            .all()
        )

        sections = {
            s.section_name: {
                "content": s.content,
                "reasoning": s.reasoning,
                "group": s.section_group,
            }
            for s in section_rows
        }

        return {
            "solution_public_id": solution_public_id,
            "blueprint_version": version_row.blueprint_version,
            "correlation_id": version_row.correlation_id,
            "sections": sections,
            "audit": {
                "module_version": version_row.module_version,
                "prompt_version": version_row.prompt_version,
                "model_version": version_row.model_version,
                "temperature": version_row.temperature,
                "audit_hash": version_row.audit_hash,
            },
        }


def list_blueprint_versions(solution_public_id: str) -> List[Dict[str, Any]]:
    """Read-only. Every version generated for this solution_public_id,
    oldest first."""
    with get_session() as session:
        rows = (
            session.query(BusinessBlueprintVersion)
            .filter(BusinessBlueprintVersion.solution_public_id == solution_public_id)
            .order_by(BusinessBlueprintVersion.blueprint_version.asc())
            .all()
        )
        return [
            {
                "blueprint_version": r.blueprint_version,
                "is_active": r.is_active,
                "created_at": r.created_at,
            }
            for r in rows
        ]
