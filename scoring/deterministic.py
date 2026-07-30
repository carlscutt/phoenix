"""
Deterministic scoring layer.

Pure arithmetic over evidence statistics already stored on a cluster —
no ModelService call, fully reproducible. Covers:

  - Frequency              (§8.1, weight 20%)
  - Evidence Confidence    (§8.3, weight 10%)
  - Commercial Confidence  (report-level-per-entry rating, Decision 1 —
                             distinct from Module 1's report confidence)

All three are relative to the run they belong to (see module docstring
note on Frequency below) rather than fixed absolute thresholds. This is
an implementation decision, not dictated by the spec — flagged in the
handoff doc for Carl to confirm or override.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ClusterEvidenceStats:
    """The minimal shape deterministic.py needs from a cluster.

    Built from phoenix.models.ComplaintCluster (+ its complaints) by the
    caller in report.py — kept as a plain dataclass here so this module
    has no ORM/session dependency and stays trivially unit-testable.
    """

    cluster_id: int
    complaint_count: int
    unique_source_types: int
    total_known_source_types: int  # e.g. 2 while only reddit+github are live


def compute_frequency(stats: ClusterEvidenceStats, all_stats: Sequence[ClusterEvidenceStats]) -> float:
    """
    Frequency score, 0-100, relative to the most-reported cluster in this
    run. A cluster with the highest complaint_count in the run scores 100;
    others scale proportionally.

    Relative (not absolute-threshold) scaling is a deliberate choice: raw
    complaint counts aren't comparable across topics or collector
    coverage, so "how often, relative to everything else surfaced this
    run" is the only fair scale available without external data.
    """
    if not all_stats:
        return 0.0
    max_count = max(s.complaint_count for s in all_stats)
    if max_count <= 0:
        return 0.0
    return round(100.0 * stats.complaint_count / max_count, 2)


def compute_evidence_confidence(stats: ClusterEvidenceStats) -> float:
    """
    Evidence Confidence score, 0-100, from source diversity and volume.

    Known limitation: with only one live collector (Reddit) approved,
    unique_source_types will be 1 for every cluster until more collectors
    ship, making the diversity term constant / uninformative in practice.
    Documented in the handoff — not something this function can fix.
    """
    if stats.total_known_source_types <= 0:
        diversity_component = 0.0
    else:
        diversity_component = min(
            1.0, stats.unique_source_types / stats.total_known_source_types
        )
    # Volume component: saturates at 10+ complaints so a handful of very
    # noisy clusters don't dominate purely on count.
    volume_component = min(1.0, stats.complaint_count / 10.0)

    score = 100.0 * (0.6 * diversity_component + 0.4 * volume_component)
    return round(score, 2)


def compute_commercial_confidence(
    stats: ClusterEvidenceStats, unknown_category_count: int, total_category_count: int
) -> str:
    """
    Commercial Confidence rating (Low/Medium/High) — Decision 1.

    Distinct from Module 1's report-level confidence. Reflects evidence
    quality behind *this specific opportunity's score*, not the whole
    report.

    Basis: evidence volume, source diversity, and how many of the 8
    scoring categories actually resolved to a real value vs. Unknown.
    This is a first-pass heuristic, explicitly tunable — same treatment
    as Module 1's original confidence formula.
    """
    resolved_ratio = (
        1.0
        if total_category_count == 0
        else 1.0 - (unknown_category_count / total_category_count)
    )

    if stats.complaint_count >= 5 and stats.unique_source_types >= 2 and resolved_ratio >= 0.75:
        return "High"
    if stats.complaint_count >= 2 and resolved_ratio >= 0.5:
        return "Medium"
    return "Low"
