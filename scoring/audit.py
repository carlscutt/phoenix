"""
Audit hash — Decision 7.

SHA-256 over: input evidence + prompt version + model version + the final
OpportunityScoreReport. Lets any report be verified against its claimed
inputs after the fact.

The report's own `hash` field is necessarily excluded from what gets
hashed (a field can't hash itself) — compute_report_hash is always called
with the report dict *before* the hash field is attached.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


def _canonical(obj: Any) -> str:
    """Stable, order-independent JSON serialisation for hashing."""
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def compute_report_hash(
    input_evidence: List[Dict[str, Any]],
    prompt_version: str,
    model_version: str,
    report_without_hash: Dict[str, Any],
) -> str:
    """
    Args:
        input_evidence: the exact evidence set scored (cluster stats +
            raw snippets used), serialisable.
        prompt_version: e.g. ai_scoring.PROMPT_VERSION
        model_version: identifying string/tag for the model used
        report_without_hash: the assembled OpportunityScoreReport dict
            with its `audit.hash` field omitted or set to None

    Returns:
        Hex-encoded SHA-256 digest.
    """
    payload = _canonical(
        {
            "input_evidence": input_evidence,
            "prompt_version": prompt_version,
            "model_version": model_version,
            "report": report_without_hash,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
