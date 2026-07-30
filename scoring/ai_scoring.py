"""
AI-assisted scoring layer.

Covers the six categories that require judgment beyond arithmetic:
Severity, Market Demand, Revenue Potential, Competition Saturation,
Automation Potential, Time To First Revenue.

Determinism (Decision 3) is achieved by pinning PROMPT_VERSION and
calling ModelService at temperature=0. Reproducibility holds *within* a
given (model_version, prompt_version) pair, not across a model upgrade —
a model/prompt change is a new scoring_version, documented, not silently
absorbed.

Calls are batched across clusters (one call per batch, not one call per
cluster per category) per the batching discipline already established in
Module 1's extraction.py and Module 2's theming.py.

ASSUMPTION FLAGGED FOR VERIFICATION: this module calls
`model_service.complete(prompt, temperature=...)` returning raw text,
mirroring the shape Research Factory is documented to use against
`get_model_service()`. If the real ModelService exposes a different
method name/signature, only `_call_model()` below needs to change —
everything else is decoupled from the exact client shape.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Sequence

from phoenix.scoring.deterministic import ClusterEvidenceStats
from phoenix.scoring.weighting import UNKNOWN

logger = logging.getLogger(__name__)

PROMPT_VERSION = "phoenix-module3-ai-scoring-v1"
TEMPERATURE = 0.0
DEFAULT_BATCH_SIZE = 5

# Corrected 2026-07-28 against the real shared_services/contracts/model_service.py
# and shared_services/model/ollama_model_service.py:
#   - ModelService.complete() signature is complete(prompt, model=None, **kwargs) —
#     there is no `temperature` keyword. OllamaModelService forwards Ollama's own
#     "options" dict (temperature, num_ctx, etc.) through kwargs["options"], so
#     temperature must be passed as options={"temperature": TEMPERATURE}, not as
#     a top-level kwarg (that would previously have raised or been silently ignored
#     depending on how **kwargs was handled downstream — worth having caught before
#     a real run, not during one).
#   - model=None lets OllamaModelService fall back to whatever
#     ConfigurationService currently has as the default model. For Decision 3's
#     "version deterministic through pinned Model Version" to actually hold,
#     Module 3 must pass an EXPLICIT model name rather than rely on that
#     config-driven default, which could change without Module 3 knowing —
#     silently breaking the reproducibility the audit hash claims to guarantee.
#     score_clusters_ai() now takes `model` and threads it through; report.py
#     supplies it.
DEFAULT_MODEL = "qwen3-coder:30b"  # matches OllamaModelService's own default —
# confirm with Carl whether Module 3 should pin this independently, or read it
# from ConfigurationService itself at scoring_version-creation time so a
# deliberate model upgrade there is still visible/auditable rather than baked
# into this constant.

AI_CATEGORIES = (
    "severity",
    "market_demand",
    "revenue_potential",
    "competition_saturation",
    "automation_potential",
    "time_to_first_revenue",
)


@dataclass(frozen=True)
class ClusterForScoring:
    """Input shape ai_scoring.py needs per cluster."""

    cluster_id: int
    representative_text: str
    evidence_snippets: List[str]  # raw complaint text, capped by caller


def _build_prompt(batch: Sequence[ClusterForScoring]) -> str:
    clusters_block = []
    for c in batch:
        snippets = "\n".join(f"    - {s}" for s in c.evidence_snippets[:5])
        clusters_block.append(
            f'  cluster_id: {c.cluster_id}\n'
            f'  problem_statement: "{c.representative_text}"\n'
            f"  evidence:\n{snippets or '    (no raw snippets available)'}"
        )
    clusters_text = "\n\n".join(clusters_block)

    return f"""You are scoring business opportunities using ONLY the evidence given below.
Do not use outside knowledge of markets, competitors, or search trends.
If the evidence does not support a judgment for a category, you MUST return
the literal string "Unknown" for that category — never guess a number.

For each cluster, score these six categories on a 0-100 scale (or "Unknown"):

- severity: how painful is this problem for the people describing it?
- market_demand: is there language suggesting people are actively trying to
  pay for or urgently seeking a solution? (Evidence-only — no search/CPC data.)
- revenue_potential: could this plausibly support a SaaS, digital product,
  subscription, service, marketplace, or affiliate model?
- competition_saturation: does the evidence suggest existing solutions people
  are unhappy with (lower saturation implied) or no mention of alternatives at
  all (return "Unknown" if evidence doesn't speak to this)?
- automation_potential: could building, marketing, or supporting a solution to
  this be substantially automated?
- time_to_first_revenue: relative-ranking only (not a real prediction) — how
  quickly could a simple MVP plausibly reach a first paying customer relative
  to a typical SaaS idea?

Clusters:

{clusters_text}

Respond with ONLY a JSON array, one object per cluster, no prose, no markdown
fences:

[
  {{
    "cluster_id": <int>,
    "severity": <0-100 or "Unknown">,
    "market_demand": <0-100 or "Unknown">,
    "revenue_potential": <0-100 or "Unknown">,
    "competition_saturation": <0-100 or "Unknown">,
    "automation_potential": <0-100 or "Unknown">,
    "time_to_first_revenue": <0-100 or "Unknown">,
    "reasoning": "<one sentence, evidence you used, evidence missing>"
  }}
]
"""


def _call_model(model_service, prompt: str, model: str) -> str:
    """
    Thin seam over the real ModelService client. Signature confirmed
    against shared_services/contracts/model_service.py and
    ollama_model_service.py: complete(prompt, model=None, **kwargs),
    temperature passed via Ollama's own options dict.
    """
    return model_service.complete(prompt, model=model, options={"temperature": TEMPERATURE})


def _parse_response(raw_text: str, expected_ids: Sequence[int]) -> Dict[int, dict]:
    """
    Parse and validate the model's JSON array. Any cluster missing from
    the response, or with a malformed entry, falls back to all-Unknown
    for that cluster rather than raising — a partial/malformed model
    response should degrade to Unknown, not take down the whole batch.
    """
    results: Dict[int, dict] = {}
    try:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        logger.warning("ai_scoring: failed to parse model response as JSON")
        parsed = []

    by_id = {}
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and "cluster_id" in item:
                by_id[item["cluster_id"]] = item

    for cid in expected_ids:
        item = by_id.get(cid)
        entry = {"reasoning": ""}
        for cat in AI_CATEGORIES:
            value = item.get(cat) if item else None
            if isinstance(value, (int, float)) and 0 <= value <= 100:
                entry[cat] = float(value)
            else:
                entry[cat] = UNKNOWN
        if item:
            entry["reasoning"] = str(item.get("reasoning", ""))
        results[cid] = entry

    return results


def score_clusters_ai(
    model_service,
    clusters: Sequence[ClusterForScoring],
    batch_size: int = DEFAULT_BATCH_SIZE,
    model: str = DEFAULT_MODEL,
) -> Dict[int, dict]:
    """
    Score all given clusters across the six AI-assisted categories,
    batched. Returns {cluster_id: {category: value_or_Unknown, reasoning}}.

    `model` is passed explicitly (not left as None) so the model actually
    used is pinned and auditable, per Decision 3 — see DEFAULT_MODEL note
    above.
    """
    results: Dict[int, dict] = {}
    for start in range(0, len(clusters), batch_size):
        batch = clusters[start : start + batch_size]
        prompt = _build_prompt(batch)
        raw_text = _call_model(model_service, prompt, model=model)
        parsed = _parse_response(raw_text, [c.cluster_id for c in batch])
        results.update(parsed)
    return results
