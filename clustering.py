"""
Complaint clustering — Module 1 step 5 (PHOENIX_ARCHITECTURE.md §3).

Mechanical near-duplicate merging ONLY. Deterministic, text-similarity
based — explicitly NOT a model call, per the architecture doc: "This
is proposed as deterministic (text-similarity based), not another
model call — matches 'deterministic wherever practical'."

Confirmed Module 1 / Module 2 boundary (approved architecture
decisions, #3): this module merges near-identical complaints into a
single complaint with an occurrence count — e.g. the same complaint
surfacing on Reddit and in a GitHub issue becomes one cluster, not
two. It does NOT do semantic/thematic grouping (e.g. "CV rewriting" +
"cover letters" + "ATS optimisation" → "Recruitment Administration")
— that's Module 2's job, out of scope here.

Uses stdlib `difflib.SequenceMatcher` (no extra dependency) as the
similarity measure over normalized (lowercased, whitespace-collapsed)
text. Clustering is greedy and order-dependent by design — given a
fixed input order and threshold, the result is always the same, which
is the point of "deterministic wherever practical."
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from phoenix.extraction import ExtractedComplaint

DEFAULT_SIMILARITY_THRESHOLD = 0.75


@dataclass
class ComplaintClusterResult:
    """One cluster of near-identical complaints. `complaint_indices`
    are positions into the original `complaints` list passed to
    `cluster_complaints()`, so the caller can map back to full
    `ExtractedComplaint` records (including source_url) for storage.
    """

    representative_text: str
    complaint_indices: list[int]
    occurrence_count: int
    source_diversity: int


def cluster_complaints(
    complaints: list[ExtractedComplaint],
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[ComplaintClusterResult]:
    """Greedily merge near-identical complaints. Each complaint joins
    the first existing cluster whose representative text scores
    highest above `similarity_threshold` (0–1, `difflib` ratio); if
    none qualifies, it starts a new cluster with itself as the
    representative.
    """
    if not (0.0 < similarity_threshold <= 1.0):
        raise ValueError(
            "similarity_threshold must be between 0 (exclusive) and 1 (inclusive)"
        )
    if not complaints:
        return []

    # (representative_text, [indices]) — built up in one pass
    clusters: list[tuple[str, list[int]]] = []

    for idx, complaint in enumerate(complaints):
        normalized = _normalize(complaint.complaint_text)

        best_cluster_pos = None
        best_score = 0.0
        for pos, (rep_text, _indices) in enumerate(clusters):
            score = _similarity(normalized, _normalize(rep_text))
            if score >= similarity_threshold and score > best_score:
                best_cluster_pos = pos
                best_score = score

        if best_cluster_pos is not None:
            clusters[best_cluster_pos][1].append(idx)
        else:
            clusters.append((complaint.complaint_text, [idx]))

    results: list[ComplaintClusterResult] = []
    for rep_text, indices in clusters:
        source_types = {complaints[i].source_type for i in indices}
        results.append(
            ComplaintClusterResult(
                representative_text=rep_text,
                complaint_indices=indices,
                occurrence_count=len(indices),
                source_diversity=len(source_types),
            )
        )
    return results


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()
