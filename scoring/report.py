"""
Report orchestrator for Module 3.

score_run(run_id) is the single entry point: pulls a run's clusters
(+ active theme version, if any), runs the deterministic and AI-assisted
layers, combines them via weighting.py, persists a new ScoringVersion,
and returns the assembled OpportunityScoreReport dict.

Corrected 2026-07-28 against Carl's real schema:
  - ComplaintCluster.phoenix_run_id (not run_id); occurrence_count and
    source_diversity are read directly from the cluster row (Module 1
    already computes these) rather than recounted from Complaint rows.
    This matters concretely: seed_test_report.py creates clusters with
    occurrence_count set but zero actual Complaint child rows — counting
    Complaint rows would have wrongly flagged those as Insufficient
    Evidence.
  - Complaint rows are still queried, but only for raw text (AI prompt
    input) and source_url/source_type (evidence refs) — not for counting.
  - ThemeVersion.phoenix_run_id (not run_id); OpportunityTheme.theme_name
    (not label).
  - get_session() already commits on clean exit (see phoenix/db.py) —
    the manual mid-function session.commit() from the first draft was
    redundant and has been removed.

Corrected again 2026-07-28 (second pass, against Carl's real
shared_services package):
  - get_model_service()/get_logging_service() confirmed real: no
    dependency-injection hook exists in the real registry.py (it's
    @lru_cache-wrapped, always constructs a real service) — tests now
    monkeypatch these names as imported into this module instead.
  - ModelService.complete()'s real signature is
    complete(prompt, model=None, **kwargs), temperature passed via
    Ollama's own options dict — not a `temperature` kwarg. Fixed in
    ai_scoring.py; model_used is now actually passed through to the
    call (previously it was only recorded in the audit trail, never
    used for the real request — see ai_scoring.py's DEFAULT_MODEL note
    on why pinning it explicitly matters for Decision 3).
  - LoggingService.log_event()'s `detail` parameter is dict[str, Any],
    not a free string — fixed in _log() below.

Only two items from PHOENIX_MODULE3_HANDOFF.md §1 remain unverified:
the approved-collector count backing TOTAL_KNOWN_SOURCE_TYPES, and an
end-to-end run against real (non-seeded) data.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from phoenix.db import get_session
from phoenix.models import (
    PhoenixRun,
    ComplaintCluster,
    Complaint,
    OpportunityTheme,
    ThemeVersion,
    ThemeClusterAssignment,
)
from phoenix.scoring.models import ScoringVersion, OpportunityScoreEntry
from phoenix.scoring.deterministic import (
    ClusterEvidenceStats,
    compute_frequency,
    compute_evidence_confidence,
    compute_commercial_confidence,
)
from phoenix.scoring.ai_scoring import (
    ClusterForScoring,
    score_clusters_ai,
    PROMPT_VERSION,
    TEMPERATURE,
    AI_CATEGORIES,
    DEFAULT_MODEL,
)
from phoenix.scoring.weighting import compute_weighted_score, UNKNOWN, CATEGORY_WEIGHTS
from phoenix.scoring.audit import compute_report_hash
from phoenix.scoring.exceptions import NoScorableInputError, ScoringVersionNotFoundError

from shared_services.registry import get_model_service, get_logging_service

MODULE_VERSION = "phoenix-module3-v1"
TOTAL_KNOWN_SOURCE_TYPES = 2  # Reddit + GitHub — see handoff doc §1
MIN_EVIDENCE_COUNT = 1  # §9 threshold: occurrence_count 0 -> Insufficient Evidence


def _log(event_type: str, run_id: int, message: str, severity: str = "info") -> None:
    """
    Corrected 2026-07-28: LoggingService.log_event()'s `detail` parameter
    is dict[str, Any] | None per the real contract, not a free string —
    wrap the message accordingly.
    """
    try:
        logging_service = get_logging_service()
        logging_service.log_event(
            source="phoenix",
            event_type=event_type,
            detail={"message": message},
            component="scoring",
            severity=severity,
            correlation_id=str(run_id),
        )
    except Exception:
        # Logging must never break a scoring run.
        pass


def _load_cluster_data(session, run_id: int) -> List[Dict[str, Any]]:
    """
    Pull clusters for a run into plain dicts. complaint_count and
    unique_source_types come from the cluster's own occurrence_count /
    source_diversity fields (Module 1 already computes these) — NOT
    recounted from Complaint rows, since a cluster can legitimately have
    those stats set with zero live Complaint children (e.g. seeded test
    data). Complaint rows are only used for raw text / evidence refs.
    """
    clusters = (
        session.query(ComplaintCluster)
        .filter(ComplaintCluster.phoenix_run_id == run_id)
        .all()
    )
    data = []
    for cluster in clusters:
        complaints = (
            session.query(Complaint).filter(Complaint.cluster_id == cluster.id).all()
        )
        data.append(
            {
                "cluster_id": cluster.id,
                "representative_text": cluster.representative_text or "",
                "complaint_count": cluster.occurrence_count,
                "unique_source_types": cluster.source_diversity,
                "evidence_snippets": [c.complaint_text for c in complaints if c.complaint_text],
                "evidence_refs": [
                    {"source_url": c.source_url, "source_type": c.source_type}
                    for c in complaints
                ],
            }
        )
    return data


def _load_active_theme_map(session, run_id: int) -> tuple[Optional[int], Dict[int, int]]:
    """Returns (active_theme_version_id, {cluster_id: theme_id}) — empty if no themes exist."""
    active_version = (
        session.query(ThemeVersion)
        .filter(ThemeVersion.phoenix_run_id == run_id, ThemeVersion.is_active.is_(True))
        .first()
    )
    if not active_version:
        return None, {}

    assignments = (
        session.query(ThemeClusterAssignment)
        .join(OpportunityTheme, ThemeClusterAssignment.theme_id == OpportunityTheme.id)
        .filter(OpportunityTheme.theme_version_id == active_version.id)
        .all()
    )
    theme_map = {a.cluster_id: a.theme_id for a in assignments}
    return active_version.id, theme_map


def _recommended_priority(rank: int, total: int) -> str:
    """
    Priority bands by rank percentile among scored (non-Insufficient
    Evidence) entries. Implementation decision, not spec-dictated —
    top ~20% High, next ~30% Medium, remainder Low. Flag for Carl to
    confirm/override if a different banding is wanted.
    """
    if total <= 0:
        return "Low"
    percentile = rank / total
    if percentile <= 0.2:
        return "High"
    if percentile <= 0.5:
        return "Medium"
    return "Low"


def score_run(
    run_id: int,
    batch_size: int = 5,
    model_used: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    Score all clusters for a PhoenixRun. Persists a new ScoringVersion
    (deactivating any prior active version for this run) and returns the
    assembled OpportunityScoreReport dict.
    """
    with get_session() as session:
        run = session.query(PhoenixRun).filter(PhoenixRun.id == run_id).first()
        if run is None:
            raise NoScorableInputError(f"PhoenixRun {run_id} not found")

        cluster_rows = _load_cluster_data(session, run_id)
        if not cluster_rows:
            raise NoScorableInputError(f"PhoenixRun {run_id} has no clusters to score")

        theme_version_id, theme_map = _load_active_theme_map(session, run_id)

        # --- split scorable vs insufficient-evidence clusters (§9/§13) ---
        scorable = [c for c in cluster_rows if c["complaint_count"] >= MIN_EVIDENCE_COUNT]
        insufficient = [c for c in cluster_rows if c["complaint_count"] < MIN_EVIDENCE_COUNT]

        all_stats = [
            ClusterEvidenceStats(
                cluster_id=c["cluster_id"],
                complaint_count=c["complaint_count"],
                unique_source_types=c["unique_source_types"],
                total_known_source_types=TOTAL_KNOWN_SOURCE_TYPES,
            )
            for c in scorable
        ]

        # --- AI-assisted layer, batched ---
        model_service = get_model_service()
        ai_inputs = [
            ClusterForScoring(
                cluster_id=c["cluster_id"],
                representative_text=c["representative_text"],
                evidence_snippets=c["evidence_snippets"],
            )
            for c in scorable
        ]
        ai_results = score_clusters_ai(
            model_service, ai_inputs, batch_size=batch_size, model=model_used
        )

        # --- combine per cluster ---
        entries: List[Dict[str, Any]] = []
        stats_by_id = {s.cluster_id: s for s in all_stats}
        for c in scorable:
            cid = c["cluster_id"]
            stats = stats_by_id[cid]
            ai = ai_results.get(cid, {cat: UNKNOWN for cat in AI_CATEGORIES})

            frequency = compute_frequency(stats, all_stats)
            evidence_confidence = compute_evidence_confidence(stats)

            category_values = {
                "frequency": frequency,
                "evidence_confidence": evidence_confidence,
                **{cat: ai.get(cat, UNKNOWN) for cat in AI_CATEGORIES},
            }
            overall_score, weights_applied = compute_weighted_score(category_values)

            unknown_count = sum(1 for v in category_values.values() if v == UNKNOWN)
            commercial_confidence = compute_commercial_confidence(
                stats, unknown_count, total_category_count=len(CATEGORY_WEIGHTS)
            )

            evidence_missing = [cat for cat, v in category_values.items() if v == UNKNOWN]

            entries.append(
                {
                    "opportunity_id": cid,
                    "theme_id": theme_map.get(cid),
                    "overall_score": overall_score,
                    "score_breakdown": {
                        cat: {
                            "value": category_values[cat],
                            "weight": CATEGORY_WEIGHTS[cat],
                            "basis": "deterministic"
                            if cat in ("frequency", "evidence_confidence")
                            else "ai_assisted",
                        }
                        for cat in CATEGORY_WEIGHTS
                    },
                    "weights_applied": weights_applied,
                    "commercial_confidence": commercial_confidence,
                    "scoring_explanation": {
                        "why": ai.get("reasoning", ""),
                        "evidence_used": c["evidence_refs"][:5],
                        "evidence_missing": evidence_missing,
                        "uncertainties": evidence_missing,
                        "assumptions": [
                            "Frequency and Time-to-first-revenue are relative rankings "
                            "within this run, not absolute predictions."
                        ],
                    },
                    "supporting_evidence_refs": c["evidence_refs"],
                    "status": "Scored",
                }
            )

        for c in insufficient:
            entries.append(
                {
                    "opportunity_id": c["cluster_id"],
                    "theme_id": theme_map.get(c["cluster_id"]),
                    "overall_score": None,
                    "score_breakdown": {},
                    "weights_applied": {},
                    "commercial_confidence": None,
                    "scoring_explanation": {
                        "why": "Insufficient evidence to score.",
                        "evidence_used": [],
                        "evidence_missing": list(CATEGORY_WEIGHTS.keys()),
                        "uncertainties": ["occurrence_count below the minimum evidence threshold."],
                        "assumptions": [],
                    },
                    "supporting_evidence_refs": [],
                    "status": "Insufficient Evidence",
                }
            )

        # --- rank + priority (scored entries only) ---
        scored_entries = [e for e in entries if e["status"] == "Scored"]
        scored_entries.sort(key=lambda e: e["overall_score"], reverse=True)
        for i, e in enumerate(scored_entries, start=1):
            e["ranking_position"] = i
            e["recommended_priority"] = _recommended_priority(i, len(scored_entries))
        for e in entries:
            if e["status"] != "Scored":
                e["ranking_position"] = None
                e["recommended_priority"] = None

        # --- assemble report, compute hash, persist ---
        prior_active = (
            session.query(ScoringVersion)
            .filter(ScoringVersion.phoenix_run_id == run_id, ScoringVersion.is_active.is_(True))
            .first()
        )
        next_version_number = (
            session.query(ScoringVersion)
            .filter(ScoringVersion.phoenix_run_id == run_id)
            .count()
            + 1
        )
        if prior_active:
            prior_active.is_active = False

        report_body = {
            "run_id": run_id,
            "scoring_version": next_version_number,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "module_version": MODULE_VERSION,
            "theme_version_id": theme_version_id,
            "entries": entries,
        }
        evidence_count = sum(c["complaint_count"] for c in cluster_rows)
        report_hash = compute_report_hash(
            input_evidence=[c["evidence_refs"] for c in cluster_rows],
            prompt_version=PROMPT_VERSION,
            model_version=model_used,
            report_without_hash=report_body,
        )

        scoring_version_row = ScoringVersion(
            phoenix_run_id=run_id,
            scoring_version=next_version_number,
            is_active=True,
            theme_version_id=theme_version_id,
            module_version=MODULE_VERSION,
            prompt_version=PROMPT_VERSION,
            model_used=model_used,
            temperature=TEMPERATURE,
            evidence_count=evidence_count,
            hash=report_hash,
        )
        session.add(scoring_version_row)
        session.flush()  # populate scoring_version_row.id

        for e in entries:
            session.add(
                OpportunityScoreEntry(
                    scoring_version_id=scoring_version_row.id,
                    cluster_id=e["opportunity_id"],
                    theme_id=e["theme_id"],
                    overall_score=e["overall_score"],
                    status=e["status"],
                    commercial_confidence=e["commercial_confidence"],
                    recommended_priority=e["recommended_priority"],
                    ranking_position=e["ranking_position"],
                    score_breakdown=e["score_breakdown"],
                    weights_applied=e["weights_applied"],
                    scoring_explanation=e["scoring_explanation"],
                    supporting_evidence_refs=e["supporting_evidence_refs"],
                )
            )
        # get_session() commits automatically on clean exit — no manual
        # session.commit() needed here (real db.py, see module docstring).

        report_body["audit"] = {
            "module_version": MODULE_VERSION,
            "prompt_version": PROMPT_VERSION,
            "model_used": model_used,
            "temperature": TEMPERATURE,
            "evidence_count": evidence_count,
            "scoring_version": next_version_number,
            "timestamp": report_body["generated_at"],
            "hash": report_hash,
        }

        _log(
            "scoring_run_completed",
            run_id,
            f"scored {len(scored_entries)} clusters, "
            f"{len(insufficient)} insufficient-evidence, version {next_version_number}",
        )

        return report_body


def get_score_report(run_id: int, scoring_version: Optional[int] = None) -> Dict[str, Any]:
    """Fetch a persisted score report — the active version by default, or a specific one."""
    with get_session() as session:
        query = session.query(ScoringVersion).filter(ScoringVersion.phoenix_run_id == run_id)
        version_row = (
            query.filter(ScoringVersion.scoring_version == scoring_version).first()
            if scoring_version is not None
            else query.filter(ScoringVersion.is_active.is_(True)).first()
        )
        if version_row is None:
            raise ScoringVersionNotFoundError(
                f"No scoring version {scoring_version or '(active)'} for run {run_id}"
            )

        entries = (
            session.query(OpportunityScoreEntry)
            .filter(OpportunityScoreEntry.scoring_version_id == version_row.id)
            .order_by(OpportunityScoreEntry.ranking_position.is_(None), OpportunityScoreEntry.ranking_position)
            .all()
        )

        return {
            "run_id": run_id,
            "scoring_version": version_row.scoring_version,
            "generated_at": version_row.created_at.isoformat(),
            "module_version": version_row.module_version,
            "theme_version_id": version_row.theme_version_id,
            "entries": [
                {
                    "opportunity_id": e.cluster_id,
                    "theme_id": e.theme_id,
                    "overall_score": e.overall_score,
                    "score_breakdown": e.score_breakdown,
                    "weights_applied": e.weights_applied,
                    "commercial_confidence": e.commercial_confidence,
                    "recommended_priority": e.recommended_priority,
                    "ranking_position": e.ranking_position,
                    "scoring_explanation": e.scoring_explanation,
                    "supporting_evidence_refs": e.supporting_evidence_refs,
                    "status": e.status,
                }
                for e in entries
            ],
            "audit": {
                "module_version": version_row.module_version,
                "prompt_version": version_row.prompt_version,
                "model_used": version_row.model_used,
                "temperature": version_row.temperature,
                "evidence_count": version_row.evidence_count,
                "scoring_version": version_row.scoring_version,
                "timestamp": version_row.created_at.isoformat(),
                "hash": version_row.hash,
            },
        }


def list_score_versions(run_id: int) -> List[Dict[str, Any]]:
    """List all scoring versions for a run, newest first."""
    with get_session() as session:
        rows = (
            session.query(ScoringVersion)
            .filter(ScoringVersion.phoenix_run_id == run_id)
            .order_by(ScoringVersion.scoring_version.desc())
            .all()
        )
        return [
            {
                "scoring_version": r.scoring_version,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat(),
                "evidence_count": r.evidence_count,
                "model_used": r.model_used,
                "hash": r.hash,
            }
            for r in rows
        ]
