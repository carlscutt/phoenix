"""
Opportunity Report assembly — Module 1 steps 6/7 (PHOENIX_ARCHITECTURE.md §3).

Assembles the final structured Opportunity Report from extraction +
clustering output. Schema matches §3 step 6, extended with the
confidence fields from the approved architecture decisions (#7):
every report must carry a confidence score supported by evidence
(complaints analysed, unique clusters, sources analysed, time period
covered) and must always explain *why* that score was assigned — not
just state a number.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from phoenix.clustering import ComplaintClusterResult
from phoenix.extraction import ExtractedComplaint

# --- confidence heuristic tunables -------------------------------------
# APPROVED AS A FIRST-PASS HEURISTIC, NOT A SETTLED ALGORITHM (per the
# approved architecture decision) — flagged explicitly so it's tuned
# deliberately later, not mistaken for a finished formula. See
# _compute_confidence()'s docstring for the reasoning behind each term.
MIN_COMPLAINTS_FOR_FULL_VOLUME_SCORE = 20
MIN_CLUSTERS_FOR_FULL_DIVERSITY_SCORE = 5
MAX_SOURCE_DIVERSITY_CONSIDERED = 3  # v1 has only 1 source (reddit); room to grow

VOLUME_WEIGHT = 0.5
CLUSTER_DIVERSITY_WEIGHT = 0.3
SOURCE_DIVERSITY_WEIGHT = 0.2
# -------------------------------------------------------------------------


@dataclass
class OpportunityReportData:
    """Everything needed to persist an `OpportunityReport` row plus its
    full complaint/cluster detail. The caller (not-yet-built
    orchestration layer / dashboard action) decides how to write this
    against a specific `PhoenixRun`."""

    topic: str
    created_at: datetime.datetime
    sources_used: list[str]
    complaints: list[dict]  # [{complaint_text, source_url, source_type, cluster_id}]
    clusters: list[dict]  # [{cluster_id, representative_text, complaint_count, source_diversity}]
    confidence_score: float
    confidence_explanation: str
    complaints_analysed_count: int
    unique_clusters_count: int
    sources_analysed: list[str]
    time_period_start: datetime.datetime | None
    time_period_end: datetime.datetime | None


def assemble_report(
    topic: str,
    complaints: list[ExtractedComplaint],
    clusters: list[ComplaintClusterResult],
    sources_used: list[str],
    evidence_timestamps: list[datetime.datetime] | None = None,
) -> OpportunityReportData:
    """Assemble the final Opportunity Report from extraction +
    clustering output.

    `evidence_timestamps` (optional): timestamps across all collected
    evidence (e.g. Reddit post `created_utc`, converted to
    `datetime`), used to compute the time period covered. Pass `None`
    if unavailable/not tracked — `time_period_start/end` are then left
    as `None` rather than guessed.
    """
    if not topic or not topic.strip():
        raise ValueError("topic is required and cannot be empty")
    if not complaints and clusters:
        raise ValueError("clusters given without any complaints — inconsistent input")
    for cluster in clusters:
        for idx in cluster.complaint_indices:
            if idx < 0 or idx >= len(complaints):
                raise ValueError(f"cluster references out-of-range complaint index {idx}")

    complaint_to_cluster: dict[int, int] = {}
    for cluster_id, cluster in enumerate(clusters):
        for idx in cluster.complaint_indices:
            complaint_to_cluster[idx] = cluster_id

    complaints_payload = [
        {
            "complaint_text": complaint.complaint_text,
            "source_url": complaint.source_url,
            "source_type": complaint.source_type,
            "cluster_id": complaint_to_cluster.get(i),
        }
        for i, complaint in enumerate(complaints)
    ]

    clusters_payload = [
        {
            "cluster_id": cluster_id,
            "representative_text": cluster.representative_text,
            "complaint_count": cluster.occurrence_count,
            "source_diversity": cluster.source_diversity,
        }
        for cluster_id, cluster in enumerate(clusters)
    ]

    sources_analysed = sorted(set(sources_used))

    time_period_start = min(evidence_timestamps) if evidence_timestamps else None
    time_period_end = max(evidence_timestamps) if evidence_timestamps else None

    confidence_score, confidence_explanation = _compute_confidence(
        complaints_count=len(complaints),
        clusters=clusters,
        sources_analysed=sources_analysed,
    )

    return OpportunityReportData(
        topic=topic,
        created_at=datetime.datetime.utcnow(),
        sources_used=list(sources_used),
        complaints=complaints_payload,
        clusters=clusters_payload,
        confidence_score=confidence_score,
        confidence_explanation=confidence_explanation,
        complaints_analysed_count=len(complaints),
        unique_clusters_count=len(clusters),
        sources_analysed=sources_analysed,
        time_period_start=time_period_start,
        time_period_end=time_period_end,
    )


def _compute_confidence(
    complaints_count: int,
    clusters: list[ComplaintClusterResult],
    sources_analysed: list[str],
) -> tuple[float, str]:
    """First-pass confidence heuristic. Combines three signals, each
    normalized to [0, 1] and weighted:

      1. Volume (weight VOLUME_WEIGHT): raw complaint count, capped at
         MIN_COMPLAINTS_FOR_FULL_VOLUME_SCORE. More complaints is
         stronger evidence of a real pattern, with diminishing need
         for more once there's a healthy sample.
      2. Cluster diversity (weight CLUSTER_DIVERSITY_WEIGHT): number
         of distinct clusters, capped at
         MIN_CLUSTERS_FOR_FULL_DIVERSITY_SCORE. The same complaint
         count spread across many distinct clusters is weaker/stronger
         evidence than volume alone would suggest — e.g. 20 complaints
         all in ONE cluster is a single loud complaint, not
         necessarily 20 confirmations of a broad opportunity space, so
         cluster count is tracked as its own signal.
      3. Source diversity (weight SOURCE_DIVERSITY_WEIGHT): distinct
         source_types actually analysed, capped at
         MAX_SOURCE_DIVERSITY_CONSIDERED. A pattern confirmed
         independently across multiple sources is stronger evidence
         than one source alone. In v1 (Reddit-only), this signal is
         always at its floor (1 / MAX_SOURCE_DIVERSITY_CONSIDERED) —
         intentional, and stated plainly in the explanation, since
         Module 1 v1 genuinely cannot claim cross-source confirmation
         it doesn't have.

    Zero complaints returns 0.0 with an explicit explanation rather
    than a division-by-zero or a misleadingly nonzero score.
    """
    if complaints_count == 0:
        return 0.0, (
            "No complaints were found in the evidence collected for this "
            "topic, so no confidence can be assigned."
        )

    volume_score = min(complaints_count / MIN_COMPLAINTS_FOR_FULL_VOLUME_SCORE, 1.0)
    cluster_diversity_score = min(len(clusters) / MIN_CLUSTERS_FOR_FULL_DIVERSITY_SCORE, 1.0)
    source_diversity_score = min(len(sources_analysed) / MAX_SOURCE_DIVERSITY_CONSIDERED, 1.0)

    raw_score = (
        VOLUME_WEIGHT * volume_score
        + CLUSTER_DIVERSITY_WEIGHT * cluster_diversity_score
        + SOURCE_DIVERSITY_WEIGHT * source_diversity_score
    )
    score = round(min(max(raw_score, 0.0), 1.0), 3)

    largest_cluster = max((c.occurrence_count for c in clusters), default=0)

    explanation = (
        f"Based on {complaints_count} complaint(s) analysed across "
        f"{len(clusters)} distinct cluster(s) (largest cluster: "
        f"{largest_cluster} occurrence(s)), from {len(sources_analysed)} "
        f"source type(s) ({', '.join(sources_analysed)}). "
        f"Volume contributes {volume_score:.2f}/1.00 "
        f"(capped at {MIN_COMPLAINTS_FOR_FULL_VOLUME_SCORE} complaints), "
        f"cluster diversity contributes {cluster_diversity_score:.2f}/1.00 "
        f"(capped at {MIN_CLUSTERS_FOR_FULL_DIVERSITY_SCORE} clusters), "
        f"source diversity contributes {source_diversity_score:.2f}/1.00 "
        f"(capped at {MAX_SOURCE_DIVERSITY_CONSIDERED} source types)."
    )
    if len(sources_analysed) <= 1:
        explanation += (
            " This report is based on a single source type, so it cannot "
            "confirm this complaint pattern independently across sources — "
            "treat this score as a within-source signal, not cross-source "
            "validation."
        )

    return score, explanation
