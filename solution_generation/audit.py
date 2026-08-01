"""
Module 4 (Solution Generation Engine) — audit hashing.

Per Build Order §5: reuse phoenix/scoring/audit.py::compute_report_hash
directly rather than writing a second implementation of the same idea.
This file is a thin, named wrapper — not a reimplementation — so
solution_generation/report.py has a call that reads naturally for what
it's hashing, while the actual hashing logic stays in one place.
"""

from __future__ import annotations

from typing import Any, Dict, List

from phoenix.scoring.audit import compute_report_hash


def compute_generation_hash(
    input_evidence: List[Dict[str, Any]],
    prompt_version: str,
    model_version: str,
    report_without_hash: Dict[str, Any],
) -> str:
    """
    Same shape/inputs as compute_report_hash() — the opportunity's
    evidence, the pinned prompt/model versions, and the assembled
    report body before the hash field is added. Kept as a distinct
    name (not reused verbatim as compute_report_hash) so a reader of
    solution_generation/report.py can tell at a glance which module's
    audit trail is being computed.
    """
    return compute_report_hash(
        input_evidence=input_evidence,
        prompt_version=prompt_version,
        model_version=model_version,
        report_without_hash=report_without_hash,
    )
