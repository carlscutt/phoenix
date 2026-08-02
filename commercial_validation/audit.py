"""
phoenix/commercial_validation/audit.py

Thin wrapper — same SHA-256 audit hash pattern already used twice in
this project (scoring/audit.py, solution_generation/audit.py). No new
design, deliberately.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


def compute_validation_hash(
    input_blueprint_ids: List[str],
    prompt_version: str,
    model_version: str,
    report_without_hash: Dict[str, Any],
) -> str:
    """
    SHA-256 over a stable, sorted-keys JSON payload of: the sorted list
    of solution_public_ids that went into this validation run, the
    prompt/model versions, and the report body (everything except the
    hash field itself, same convention as solution_generation/audit.py).
    """
    payload = {
        "input_blueprint_ids": sorted(input_blueprint_ids),
        "prompt_version": prompt_version,
        "model_version": model_version,
        "report": report_without_hash,
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
