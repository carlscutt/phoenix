"""
Phoenix orchestration layer — Module 1 (Opportunity Discovery), Module 2
(Thematic Grouping), and Module 3 (Commercial Opportunity Scoring)
entry points. CLI, Dashboard, and Telegram all call these same
functions — the "one execution model" pattern used throughout AI-BOS.

RECONSTRUCTED 2026-07-29: the live phoenix_actions.py was accidentally
overwritten by a Module 3 integration-addition file earlier in this
session (no git history to recover from). This is a from-scratch
rebuild against the real, still-intact source files (models.py,
source_selector.py, extraction.py, clustering.py, report.py,
theming.py, collectors/base.py, collectors/reddit_collector.py) rather
than a guess — but it is a reconstruction, not a byte-for-byte restore.
Two known simplifications, flagged rather than silently assumed:
  - evidence_timestamps is not threaded through to assemble_report()
    here (no confirmed source for converting raw.extra["created_utc"]
    to datetime existed in what survived) — report.py's own docstring
    says pass None if unavailable, so time_period_start/end will be
    None. If the original computed this, it's a small, contained
    follow-up, not a redesign.
  - Complaint.evidence_id is left unset (nullable in the schema) —
    no confirmed original wiring from ExtractedComplaint back to a
    specific Evidence row existed in what survived either.

MODULE 5 ADDITION (2026-08-01): three thin wrapper functions added at
the bottom, same shape as Module 4's own submit_solution_generation() /
get_solutions() / get_solution_versions() — nothing above this
docstring's original content changed.
"""


from __future__ import annotations

import datetime
from typing import Any

from phoenix.db import get_session
from phoenix.models import (
    PhoenixRun,
    Evidence,
    Complaint,
    ComplaintCluster,
    OpportunityReport,
    ThemeVersion,
    OpportunityTheme,
    ThemeClusterAssignment,
)

from phoenix.solution_generation.report import (
    generate_solutions,
    list_generation_versions_for_opportunity,
    get_active_solutions,
    approve_blueprint,
)
from phoenix.source_selector import select_sources
from phoenix.collectors.reddit import RedditCollector
from phoenix.collectors.base import RawEvidence
from phoenix.extraction import extract_complaints
from phoenix.clustering import cluster_complaints
from phoenix.report import assemble_report
from phoenix.theming import group_into_themes, ClusterInput, ThemeGenerationResult

from shared_services.registry import get_logging_service

# Module 3 (unaffected by the overwrite — these three are correct as-is,
# just merged back in here alongside Modules 1/2 instead of standing alone)
from phoenix.scoring.report import (
    score_run,
    get_score_report,
    list_score_versions as _list_score_versions,
)
from phoenix.scoring.exceptions import NoScorableInputError, ScoringVersionNotFoundError
from phoenix.scoring.models import ScoringVersion, OpportunityScoreEntry

# Module 5 (new)
from phoenix.commercial_validation.report import (
    validate_solutions,
    get_active_validations,
    list_validation_versions_for_opportunity,
)

# Module 6 (new)
from phoenix.business_blueprint.report import (
    generate_business_blueprint,
    get_active_blueprint,
    list_blueprint_versions,
)


class PhoenixThemeError(RuntimeError):
    """Raised when theming is attempted on a run with no OpportunityReport yet."""


# ---------------------------------------------------------------------
# Logging helpers — generalized to accept component/severity (defaults
# unchanged, so behavior for existing call sites is unaffected)
# ---------------------------------------------------------------------


def _log_event(
    event_type: str,
    run_id: int,
    detail: dict[str, Any],
    component: str = "orchestration",
    severity: str = "info",
) -> None:
    try:
        get_logging_service().log_event(
            source="phoenix",
            event_type=event_type,
            detail=detail,
            component=component,
            severity=severity,
            correlation_id=str(run_id),
        )
    except Exception:
        # Logging must never break a real run.
        pass


def _log_error(event_type: str, run_id: int, detail: dict[str, Any], component: str = "orchestration") -> None:
    try:
        get_logging_service().log_error(
            source="phoenix",
            event_type=event_type,
            detail=detail,
            component=component,
            correlation_id=str(run_id),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------
# Module 1 — Opportunity Discovery
# ---------------------------------------------------------------------


def submit_opportunity_discovery(topic: str) -> int:
    """
    Run the full Module 1 pipeline for `topic`: select sources, collect
    evidence, extract complaints, cluster them, assemble and persist an
    OpportunityReport. Returns the new PhoenixRun's id.
    """
    if not topic or not topic.strip():
        raise ValueError("topic is required and cannot be empty")

    with get_session() as session:
        run = PhoenixRun(topic=topic, status="pending")
        session.add(run)
        session.flush()
        run_id = run.id

    _log_event("run_created", run_id, {"topic": topic})

    try:
        with get_session() as session:
            run = session.query(PhoenixRun).filter(PhoenixRun.id == run_id).first()
            run.status = "running"
            run.started_at = datetime.datetime.utcnow()

        selection = select_sources(topic)
        _log_event(
            "sources_selected",
            run_id,
            {"sources": selection.sources, "starting_points": selection.starting_points},
        )

        raw_evidence: list[RawEvidence] = []
        if "reddit" in selection.sources:
            collector = RedditCollector()
            queries = selection.starting_points.get("reddit") or [topic]
            for query in queries:
                raw_evidence.extend(collector.fetch(query))

        with get_session() as session:
            for raw in raw_evidence:
                session.add(
                    Evidence(
                        phoenix_run_id=run_id,
                        source_type=raw.source_type,
                        source_url=raw.source_url,
                        raw_snippet=raw.raw_snippet,
                        extra=raw.extra,
                    )
                )

        _log_event("evidence_collected", run_id, {"evidence_count": len(raw_evidence)})

        extracted = extract_complaints(raw_evidence)
        _log_event("complaints_extracted", run_id, {"complaint_count": len(extracted)})

        clusters = cluster_complaints(extracted)
        _log_event("complaints_clustered", run_id, {"cluster_count": len(clusters)})

        report_data = assemble_report(
            topic=topic,
            complaints=extracted,
            clusters=clusters,
            sources_used=selection.sources,
        )

        with get_session() as session:
            cluster_rows: list[ComplaintCluster] = []
            for cluster in clusters:
                cluster_row = ComplaintCluster(
                    phoenix_run_id=run_id,
                    representative_text=cluster.representative_text,
                    occurrence_count=cluster.occurrence_count,
                    source_diversity=cluster.source_diversity,
                )
                session.add(cluster_row)
                cluster_rows.append(cluster_row)
            session.flush()

            complaint_to_cluster_id: dict[int, int] = {}
            for cluster_idx, cluster in enumerate(clusters):
                for complaint_idx in cluster.complaint_indices:
                    complaint_to_cluster_id[complaint_idx] = cluster_rows[cluster_idx].id

            for i, complaint in enumerate(extracted):
                session.add(
                    Complaint(
                        phoenix_run_id=run_id,
                        complaint_text=complaint.complaint_text,
                        source_url=complaint.source_url,
                        source_type=complaint.source_type,
                        cluster_id=complaint_to_cluster_id.get(i),
                    )
                )

            session.add(
                OpportunityReport(
                    phoenix_run_id=run_id,
                    topic=report_data.topic,
                    confidence_score=report_data.confidence_score,
                    confidence_explanation=report_data.confidence_explanation,
                    complaints_analysed_count=report_data.complaints_analysed_count,
                    unique_clusters_count=report_data.unique_clusters_count,
                    sources_analysed=report_data.sources_analysed,
                    time_period_start=report_data.time_period_start,
                    time_period_end=report_data.time_period_end,
                )
            )

        _log_event("report_assembled", run_id, {"confidence_score": report_data.confidence_score})

        with get_session() as session:
            run = session.query(PhoenixRun).filter(PhoenixRun.id == run_id).first()
            run.status = "completed"
            run.finished_at = datetime.datetime.utcnow()
            run.sources_used = selection.sources

        _log_event("run_completed", run_id, {"status": "completed"})
        return run_id

    except Exception as exc:
        with get_session() as session:
            run = session.query(PhoenixRun).filter(PhoenixRun.id == run_id).first()
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.datetime.utcnow()
        _log_error("run_failed", run_id, {"error": str(exc)})
        raise


def get_report(run_id: int, theme_version: int | None = None) -> dict[str, Any]:
    """Fetch a report's full detail — clusters, complaints, and theme
    status/themes (active version by default, or a specific historical
    version via `theme_version`)."""
    with get_session() as session:
        run = session.query(PhoenixRun).filter(PhoenixRun.id == run_id).first()
        if run is None:
            raise ValueError(f"PhoenixRun {run_id} not found")

        report = (
            session.query(OpportunityReport)
            .filter(OpportunityReport.phoenix_run_id == run_id)
            .first()
        )
        clusters = (
            session.query(ComplaintCluster)
            .filter(ComplaintCluster.phoenix_run_id == run_id)
            .all()
        )
        complaints = (
            session.query(Complaint).filter(Complaint.phoenix_run_id == run_id).all()
        )

        scoring_version_row = (
            session.query(ScoringVersion)
            .filter(ScoringVersion.phoenix_run_id == run_id, ScoringVersion.is_active.is_(True))
            .first()
        )
        score_by_cluster_id: dict[int, dict] = {}
        if scoring_version_row is not None:
            entries = (
                session.query(OpportunityScoreEntry)
                .filter(OpportunityScoreEntry.scoring_version_id == scoring_version_row.id)
                .all()
            )
            score_by_cluster_id = {
                e.cluster_id: {
                    "status": e.status,
                    "overall_score": e.overall_score,
                    "commercial_confidence": e.commercial_confidence,
                }
                for e in entries
            }
        scoring_version_number = scoring_version_row.scoring_version if scoring_version_row else None

        cluster_payload = [
            {
                "cluster_id": c.id,
                "representative_text": c.representative_text,
                "complaint_count": c.occurrence_count,
                "source_diversity": c.source_diversity,
                "score": score_by_cluster_id.get(c.id),
            }
            for c in clusters
        ]
        complaint_payload = [
            {
                "complaint_text": c.complaint_text,
                "source_url": c.source_url,
                "source_type": c.source_type,
                "cluster_id": c.cluster_id,
            }
            for c in complaints
        ]

        version_query = session.query(ThemeVersion).filter(ThemeVersion.phoenix_run_id == run_id)
        theme_version_row = (
            version_query.filter(ThemeVersion.version_number == theme_version).first()
            if theme_version is not None
            else version_query.filter(ThemeVersion.is_active.is_(True)).first()
        )

        theme_status = "not_processed"
        themes_payload = None
        if theme_version_row is not None:
            theme_status = "processed"
            themes = (
                session.query(OpportunityTheme)
                .filter(OpportunityTheme.theme_version_id == theme_version_row.id)
                .all()
            )
            themes_payload = []
            for theme in themes:
                assignments = (
                    session.query(ThemeClusterAssignment)
                    .filter(ThemeClusterAssignment.theme_id == theme.id)
                    .all()
                )
                themes_payload.append(
                    {
                        "theme_id": theme.id,
                        "theme_name": theme.theme_name,
                        "rationale": theme.rationale,
                        "cluster_ids": [a.cluster_id for a in assignments],
                    }
                )

        return {
            "run_id": run_id,
            "topic": run.topic,
            "status": run.status,
            "confidence_score": report.confidence_score if report else None,
            "confidence_explanation": report.confidence_explanation if report else None,
            "complaints_analysed_count": report.complaints_analysed_count if report else 0,
            "unique_clusters_count": report.unique_clusters_count if report else 0,
            "sources_analysed": report.sources_analysed if report else [],
            "time_period_start": report.time_period_start if report else None,
            "time_period_end": report.time_period_end if report else None,
            "clusters": cluster_payload,
            "complaints": complaint_payload,
            "theme_status": theme_status,
            "theme_version": theme_version_row.version_number if theme_version_row else None,
            "theme_version_id": theme_version_row.id if theme_version_row else None,
            "themes": themes_payload,
            "score_status": "scored" if scoring_version_row is not None else "not_scored",
            "scoring_version": scoring_version_number,
        }


def list_reports() -> list[dict[str, Any]]:
    """List all runs, newest first, with a summary of each."""
    with get_session() as session:
        runs = session.query(PhoenixRun).order_by(PhoenixRun.created_at.desc()).all()
        result = []
        for run in runs:
            report = (
                session.query(OpportunityReport)
                .filter(OpportunityReport.phoenix_run_id == run.id)
                .first()
            )
            result.append(
                {
                    "run_id": run.id,
                    "topic": run.topic,
                    "status": run.status,
                    "created_at": run.created_at,
                    "confidence_score": report.confidence_score if report else None,
                    "complaints_analysed_count": report.complaints_analysed_count if report else 0,
                    "unique_clusters_count": report.unique_clusters_count if report else 0,
                    "sources_analysed": report.sources_analysed if report else [],
                }
            )
        return result


# ---------------------------------------------------------------------
# Module 2 — Thematic Grouping
# ---------------------------------------------------------------------


def theme_report(run_id: int, batch_size: int = 10) -> dict[str, Any]:
    """
    Generate (or re-generate) themes for a run's clusters. Adds a new
    ThemeVersion, deactivating any prior active version — never
    overwrites, per the approved versioning decision.
    """
    with get_session() as session:
        run = session.query(PhoenixRun).filter(PhoenixRun.id == run_id).first()
        if run is None:
            raise ValueError(f"PhoenixRun {run_id} not found")
        # Captured before the session closes — accessing run.topic after
        # the block exits raises DetachedInstanceError (real bug found
        # and fixed the same way in seed_test_report.py).
        topic = run.topic

        report = (
            session.query(OpportunityReport)
            .filter(OpportunityReport.phoenix_run_id == run_id)
            .first()
        )
        if report is None:
            raise PhoenixThemeError(
                f"PhoenixRun {run_id} has no OpportunityReport yet — run "
                "submit_opportunity_discovery first."
            )

        clusters = (
            session.query(ComplaintCluster)
            .filter(ComplaintCluster.phoenix_run_id == run_id)
            .all()
        )
        cluster_inputs = [
            ClusterInput(
                position=i,
                representative_text=c.representative_text,
                occurrence_count=c.occurrence_count,
                source_diversity=c.source_diversity,
            )
            for i, c in enumerate(clusters)
        ]
        position_to_cluster_id = {i: c.id for i, c in enumerate(clusters)}

    result: ThemeGenerationResult = group_into_themes(cluster_inputs, topic=topic, batch_size=batch_size)

    _persist_themes(run_id, result, position_to_cluster_id)

    _log_event(
        "themes_generated",
        run_id,
        {"theme_count": len(result.groups), "other_bucket_percent": result.other_bucket_percent},
        component="theming",
    )
    if result.other_bucket_exceeded:
        _log_event(
            "other_bucket_exceeded",
            run_id,
            {
                "other_bucket_percent": result.other_bucket_percent,
                "recommendation": "consider creating a new theme",
            },
            component="theming",
            severity="warning",
        )

    return get_report(run_id)


def _persist_themes(
    run_id: int, result: ThemeGenerationResult, position_to_cluster_id: dict[int, int]
) -> int:
    with get_session() as session:
        prior_active = (
            session.query(ThemeVersion)
            .filter(ThemeVersion.phoenix_run_id == run_id, ThemeVersion.is_active.is_(True))
            .first()
        )
        next_version_number = (
            session.query(ThemeVersion).filter(ThemeVersion.phoenix_run_id == run_id).count() + 1
        )
        if prior_active:
            prior_active.is_active = False

        version = ThemeVersion(
            phoenix_run_id=run_id,
            version_number=next_version_number,
            is_active=True,
            other_bucket_percent=result.other_bucket_percent,
        )
        session.add(version)
        session.flush()

        for group in result.groups:
            theme = OpportunityTheme(
                theme_version_id=version.id,
                theme_name=group.theme_name,
                rationale=group.rationale,
            )
            session.add(theme)
            session.flush()
            for position in group.cluster_positions:
                cluster_id = position_to_cluster_id.get(position)
                if cluster_id is not None:
                    session.add(ThemeClusterAssignment(theme_id=theme.id, cluster_id=cluster_id))

        return version.id


def list_theme_versions(run_id: int) -> list[dict[str, Any]]:
    """List all theme versions for a run, newest first."""
    with get_session() as session:
        versions = (
            session.query(ThemeVersion)
            .filter(ThemeVersion.phoenix_run_id == run_id)
            .order_by(ThemeVersion.version_number.desc())
            .all()
        )
        return [
            {
                "version_number": v.version_number,
                "is_active": v.is_active,
                "other_bucket_percent": v.other_bucket_percent,
                "created_at": v.created_at,
            }
            for v in versions
        ]


# ---------------------------------------------------------------------
# Module 3 — Commercial Opportunity Scoring
# ---------------------------------------------------------------------


def submit_opportunity_scoring(run_id: int, batch_size: int = 5):
    """Score a run's clusters (Module 3)."""
    try:
        return score_run(run_id, batch_size=batch_size)
    except NoScorableInputError as e:
        raise ValueError(str(e)) from e


def get_score(run_id: int, scoring_version: int | None = None):
    """Fetch a score report — active version by default, or a specific one."""
    try:
        return get_score_report(run_id, scoring_version=scoring_version)
    except ScoringVersionNotFoundError as e:
        raise ValueError(str(e)) from e


def list_scoring_versions(run_id: int):
    """List all scoring versions for a run, newest first."""
    return _list_score_versions(run_id)

# ---------------------------------------------------------------------
# Module 4 — Solution Generation Engine
# ---------------------------------------------------------------------


def submit_solution_generation(run_id: int, cluster_id: int, scoring_version: int | None = None):
    """Generate SolutionBlueprints for a single selected opportunity (Module 4)."""
    return generate_solutions(run_id, cluster_id, scoring_version=scoring_version)


def get_solutions(run_id: int, cluster_id: int, scoring_version: int | None = None):
    """
    Fetch the currently active generation's blueprints for one opportunity,
    or None if nothing has been generated yet for it.
    """
    return get_active_solutions(run_id, cluster_id, scoring_version=scoring_version)


def get_solution_versions(run_id: int, cluster_id: int, scoring_version: int | None = None):
    """List all solution generation versions for one opportunity, newest first."""
    return list_generation_versions_for_opportunity(run_id, cluster_id, scoring_version=scoring_version)


def approve_solution_blueprint(public_id: str, approved: bool = True):
    """Set the Approve Solution flag on one blueprint, by its public ID."""
    return approve_blueprint(public_id, approved=approved)


# ---------------------------------------------------------------------
# Module 5 — Commercial Validation Engine
# Same thin-wrapper pattern as Module 4 above: each function here does
# nothing but call straight into phoenix/commercial_validation/report.py.
# ---------------------------------------------------------------------


def submit_solution_validation(run_id: int, cluster_id: int, scoring_version: int | None = None):
    """Validate every active SolutionBlueprint for one opportunity (Module 5)."""
    return validate_solutions(run_id, cluster_id, scoring_version=scoring_version)


def get_validations(run_id: int, cluster_id: int):
    """
    Fetch the currently active validation's results for one opportunity,
    or None if nothing has been validated yet for it.
    """
    return get_active_validations(run_id, cluster_id)


def get_validation_versions(run_id: int, cluster_id: int):
    """List all validation versions for one opportunity, newest first."""
    return list_validation_versions_for_opportunity(run_id, cluster_id)


# ---------------------------------------------------------------------
# Module 6 — Business Blueprint Engine
# Same thin-wrapper pattern as Modules 4 and 5 above: each function here
# does nothing but call straight into phoenix/business_blueprint/report.py.
# Scoped to a single solution_public_id throughout (Decision 3, approved
# with the Module 6 Build Order) — not run_id/cluster_id alone, since a
# Business Blueprint targets one specific validated candidate, not "the
# opportunity" as a whole.
# ---------------------------------------------------------------------


def submit_business_blueprint_generation(run_id: int, cluster_id: int, solution_public_id: str):
    """Generate a Business Blueprint for one validated solution (Module 6)."""
    return generate_business_blueprint(run_id, cluster_id, solution_public_id)


def get_business_blueprint(solution_public_id: str):
    """
    Fetch the currently active Business Blueprint for a solution_public_id,
    or None if nothing has been generated yet for it.
    """
    return get_active_blueprint(solution_public_id)


def get_business_blueprint_versions(solution_public_id: str):
    """List all Business Blueprint versions for a solution_public_id, newest
    first — list_blueprint_versions() itself returns oldest-first (report.py's
    own internal convention), reversed here to match every other
    list_*_versions() wrapper's newest-first contract in this file."""
    return list(reversed(list_blueprint_versions(solution_public_id)))
