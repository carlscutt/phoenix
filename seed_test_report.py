"""
One-off seed script — creates a fake but realistic PhoenixRun +
ComplaintClusters + OpportunityReport directly in phoenix.db, so
Module 2 (theming) can be smoke-tested in Studio without waiting on
the Reddit OAuth block to clear.

This bypasses evidence collection and extraction entirely — the
clusters below are hand-written, not derived from real Reddit data.
It's meant to unblock testing "Generate themes" against your real
ModelService, not to stand in for a real Module 1 run.

Usage (from ~/projects, so the phoenix package is importable — same
requirement as everything else in phoenix/):

    python3 -m phoenix.seed_test_report

Then open Studio -> Opportunities -> the new "recruiters (seeded test)"
report -> Generate themes.

Safe to run more than once - each run creates a new, separate PhoenixRun.
Delete phoenix.db (or just the seeded run's rows) whenever you're done
with it; it's not real data and nothing else depends on it existing.
"""
from __future__ import annotations

from phoenix.db import get_session
from phoenix.models import ComplaintCluster, OpportunityReport, PhoenixRun

SAMPLE_CLUSTERS = [
    ("CV formatting is inconsistent across templates", 5, 2),
    ("Cover letters take too long to personalize for every job", 4, 2),
    ("Interview scheduling back-and-forth wastes a full day", 6, 3),
    ("Recruiters ghost candidates after the first call", 8, 4),
    ("Job descriptions are vague about actual responsibilities", 3, 2),
    ("Salary ranges are hidden until the final round", 5, 3),
    ("ATS systems reject qualified candidates for keyword mismatches", 7, 3),
    ("Reference checks take weeks to complete", 2, 1),
    ("Onboarding paperwork is duplicated across three systems", 2, 1),
    ("No feedback given after a rejected application", 6, 3),
    ("Recruiters push roles that don't match stated preferences", 3, 2),
    ("Assessment tests are disproportionate to the role's seniority", 4, 2),
]


def main() -> None:
    with get_session() as session:
        run = PhoenixRun(
            topic="recruiters (seeded test)",
            status="completed",
            sources_used=["reddit"],
        )
        session.add(run)
        session.flush()

        for text, occurrence_count, source_diversity in SAMPLE_CLUSTERS:
            session.add(
                ComplaintCluster(
                    phoenix_run_id=run.id,
                    representative_text=text,
                    occurrence_count=occurrence_count,
                    source_diversity=source_diversity,
                )
            )

        session.add(
            OpportunityReport(
                phoenix_run_id=run.id,
                topic=run.topic,
                confidence_score=0.65,
                confidence_explanation=(
                    "Seeded test data, not a real Module 1 run — confidence score "
                    "is a placeholder, not evidence-derived."
                ),
                complaints_analysed_count=sum(c[1] for c in SAMPLE_CLUSTERS),
                unique_clusters_count=len(SAMPLE_CLUSTERS),
                sources_analysed=["reddit"],
            )
        )

        run_id = run.id
        topic = run.topic

    print(f"Seeded PhoenixRun id={run_id}, topic={topic!r}")
    print(f"{len(SAMPLE_CLUSTERS)} clusters, {sum(c[1] for c in SAMPLE_CLUSTERS)} total complaints")
    print("Open Studio -> Opportunities -> the new report -> Generate themes.")


if __name__ == "__main__":
    main()
