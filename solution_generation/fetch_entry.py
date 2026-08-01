"""
Module 4 (Solution Generation Engine) — single-entry fetch.

Per MODULE_04_SPECIFICATION.md v1.3 §5: Module 4 operates on a single
selected OpportunityScoreEntry, not an entire ScoringVersion. There is
no get_single_entry() in phoenix/scoring/report.py, and none is added
there — this file calls the existing get_score_report() and filters
client-side to the one matching cluster_id. That keeps Module 4 reading
Module 3's output only through what's already published (per spec §5:
"Module 4 must never read Module 1 or Module 2 data directly"), rather
than opening a new read path into Module 3's internals.

Per spec §22a: Audit Metadata lives on the parent ScoringVersion, one
level up from the entry — so this returns the entry AND that audit
block together, since a single OpportunityScoreEntry alone doesn't
carry its own audit trail.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from phoenix.scoring.report import get_score_report
from phoenix.solution_generation.exceptions import OpportunityEntryNotFoundError


def get_opportunity_entry(
    run_id: int,
    cluster_id: int,
    scoring_version: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetch a single OpportunityScoreEntry (by cluster_id) from a Module 3
    score report, plus the audit block of the ScoringVersion it belongs
    to.

    Args:
        run_id: the PhoenixRun the score report belongs to.
        cluster_id: the specific opportunity/entry to select — this is
            what the UI's "Selected Opportunity" (spec §17) resolves to.
        scoring_version: a specific ScoringVersion number, or None for
            the currently active one (same default as get_score_report()).

    Returns:
        {
            "entry": <the one matching entry dict, same shape as
                      get_score_report()'s per-entry dicts>,
            "audit": <the report's audit block>,
            "run_id": run_id,
            "scoring_version": <the resolved scoring_version number>,
        }

    Raises:
        OpportunityEntryNotFoundError: if run_id/scoring_version exists
            but no entry matches cluster_id. (If run_id/scoring_version
            itself doesn't exist, get_score_report() raises
            ScoringVersionNotFoundError — that propagates unchanged.)
    """
    report = get_score_report(run_id, scoring_version)

    matching = [e for e in report["entries"] if e["opportunity_id"] == cluster_id]
    if not matching:
        raise OpportunityEntryNotFoundError(
            f"No OpportunityScoreEntry with cluster_id={cluster_id} in "
            f"run {run_id}, scoring_version {report['scoring_version']}"
        )

    return {
        "entry": matching[0],
        "audit": report["audit"],
        "run_id": run_id,
        "scoring_version": report["scoring_version"],
    }
