"""
ADDITIONS FOR: dashboard/phoenix_actions.py (or wherever Module 1/2's
submit_opportunity_discovery / get_report / list_reports / theme_report
already live).

This session had no filesystem access to the real project, so this is
provided as a standalone set of functions to paste in / merge — not a
diff against the live file. Function names and the (topic) -> report_id
-> ... call shape follow the same convention as the existing Module 1/2
actions (submit_opportunity_discovery, get_report, theme_report,
list_theme_versions) documented in the architecture record.

Add these alongside the existing Module 1/2 functions in the same file
(or a sibling module imported the same way) so CLI, Dashboard, and
Telegram continue to share one execution path per the "one execution
model" pattern.
"""

from phoenix.scoring.report import (
    score_run,
    get_score_report,
    list_score_versions as _list_score_versions,
)
from phoenix.scoring.exceptions import NoScorableInputError, ScoringVersionNotFoundError


def submit_opportunity_scoring(run_id: int, batch_size: int = 5):
    """
    Score a run's clusters (Module 3). Mirrors submit_opportunity_discovery's
    shape: synchronous call in, persisted report out. If a longer-running
    async pattern is preferred (matching Builder's submit_goal/resume_workflow
    split), that's a straightforward wrap around this same function — not
    something this addition assumes for you.
    """
    try:
        return score_run(run_id, batch_size=batch_size)
    except NoScorableInputError as e:
        # Surface the same way Module 1/2 surface a bad run_id today —
        # adjust to match whatever error convention the live file uses.
        raise ValueError(str(e)) from e


def get_score(run_id: int, scoring_version: int | None = None):
    """Fetch a score report — active version by default, or a specific one."""
    try:
        return get_score_report(run_id, scoring_version=scoring_version)
    except ScoringVersionNotFoundError as e:
        raise ValueError(str(e)) from e


def list_scoring_versions(run_id: int):
    """List all scoring versions for a run, newest first — mirrors list_theme_versions."""
    return _list_score_versions(run_id)
