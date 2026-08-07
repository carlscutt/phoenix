"""
phoenix/business_blueprint/audit.py

Thin wrapper — same SHA-256 audit hash pattern already used three times
in this project (scoring/audit.py, solution_generation/audit.py,
commercial_validation/audit.py). No new design, deliberately.

Module 6 hashes over a single solution_public_id (not a list, unlike
commercial_validation/audit.py's compute_validation_hash — Module 5
validates a whole set of blueprints per run, Module 6 generates one
Business Blueprint per solution_public_id). generation_version and
validation_version are included in the payload so the hash also pins
exactly which upstream Module 4/5 versions this Business Blueprint was
built against — provenance that matters here specifically because
Module 6 reads across two other modules' outputs (Decision 2), unlike
Module 5 which only ever reads one (Module 4).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def compute_business_blueprint_hash(
    solution_public_id: str,
    generation_version: int,
    validation_version: int,
    prompt_version: str,
    model_version: str,
    report_without_hash: Dict[str, Any],
) -> str:
    """
    SHA-256 over a stable, sorted-keys JSON payload of: the
    solution_public_id this Business Blueprint was generated for, the
    Module 4/5 version numbers it was built against, the prompt/model
    versions, and the report body (everything except the hash field
    itself — same convention as every other audit.py in this project).
    """
    payload = {
        "solution_public_id": solution_public_id,
        "generation_version": generation_version,
        "validation_version": validation_version,
        "prompt_version": prompt_version,
        "model_version": model_version,
        "report": report_without_hash,
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
