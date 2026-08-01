"""
Module 4 (Solution Generation Engine) — the AI-assisted generation step.

Named generator.py, not ai_generation.py (Carl, 2026-07-30 review): the
module's responsibility is generating solutions, not "being AI" — it
happens to use AI internally today, and a later version could add a
deterministic path alongside it without the filename lying about what
the module does.

Model-call contract copied directly from the real, confirmed
phoenix/scoring/ai_scoring.py — not re-derived or guessed:
  - ModelService.complete(prompt, model=None, **kwargs) — no
    `temperature` kwarg; temperature goes through Ollama's own options
    dict: options={"temperature": TEMPERATURE}.
  - model is passed explicitly (never left None) so the model actually
    used is pinned and auditable — same "Decision 3 determinism" reason
    ai_scoring.py's DEFAULT_MODEL comment gives.
  - JSON response parsing: strip markdown fences if present, then
    json.loads; a malformed or unparseable response degrades to an
    empty candidate list rather than raising — a bad model response
    should not crash the run. (Unlike ai_scoring.py's per-category
    Unknown fallback, there's no per-field "Unknown" here — a
    malformed *blueprint* just doesn't become a candidate; Blueprint
    Validation, spec §6b, is the next line of defense either way.)

Unlike ai_scoring.py, this is a single, unbatched call: one selected
OpportunityScoreEntry in, one JSON array of 3-5 solution candidates
out. There's no cross-cluster batching problem here, since Module 4
only ever operates on one entry at a time (spec §5).

This file does NOT validate candidates against patterns.py's registries
or check for duplicates — that's Blueprint Validation (spec §6b),
deliberately a separate step (see Build Order §4.5) so "did the model
respond with well-formed JSON" and "is this a business-valid blueprint"
stay two distinct, separately-testable concerns.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from phoenix.solution_generation.patterns import (
    SOLUTION_TYPES,
    COMMERCIAL_PATTERNS,
    REVENUE_MODELS,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "phoenix-module4-solution-generation-v1"
TEMPERATURE = 0.0  # same determinism rationale as ai_scoring.py (Decision 3)

# Matches ai_scoring.py's DEFAULT_MODEL today. Kept as an independent
# constant (not imported from ai_scoring.py) since Module 4's model
# choice is its own audited decision, per spec §14 — if Carl ever wants
# Module 4 on a different/newer model than Module 3, this is the one
# line that changes, and the audit hash will correctly show the two
# modules diverged on purpose, not by accident.
DEFAULT_MODEL = "qwen3-coder:30b"  # CONFIRM WITH CARL, same flag ai_scoring.py raised

MIN_SOLUTIONS = 3
MAX_SOLUTIONS = 5
CUSTOMER_TYPES = (
    "Consumer",
    "Business",
    "Enterprise",
    "Developer",
    "Creator",
    "Education",
    "Government",
)


def _build_prompt(entry: Dict[str, Any]) -> str:
    """
    entry is the dict returned by fetch_entry.get_opportunity_entry()'s
    ["entry"] key — same shape as get_score_report()'s per-entry dicts,
    plus problem_statement (Module 3 extension, spec §22a).
    """
    problem_statement = entry.get("problem_statement", "")
    why = entry.get("scoring_explanation", {}).get("why", "")
    evidence_used = entry.get("scoring_explanation", {}).get("evidence_used", [])
    evidence_lines = "\n".join(
        f"    - {e.get('source_type', 'unknown')}: {e.get('source_url', '')}"
        for e in evidence_used
    )
    commercial_score = entry.get("overall_score")
    commercial_confidence = entry.get("commercial_confidence")

    solution_types_list = ", ".join(f'"{t}"' for t in SOLUTION_TYPES)
    patterns_list = ", ".join(f'"{p}"' for p in COMMERCIAL_PATTERNS)
    revenue_list = ", ".join(f'"{r}"' for r in REVENUE_MODELS)
    customer_types_list = ", ".join(f'"{c}"' for c in CUSTOMER_TYPES)

    return f"""You are generating commercially-framed BUSINESS concepts for a
validated opportunity — not bare product ideas. "A subscription Chrome
extension" is what we want; "a Chrome extension" alone is not enough.

Use ONLY the evidence given below. Do not invent market data, revenue
estimates, or claims of validation beyond what the evidence supports.

Opportunity:
  problem_statement: "{problem_statement}"
  scoring_reasoning: "{why}"
  commercial_score: {commercial_score}
  commercial_confidence: {commercial_confidence}
  evidence_sample:
{evidence_lines or '    (no evidence sample available)'}

Generate between {MIN_SOLUTIONS} and {MAX_SOLUTIONS} materially different
solution concepts (business models, not variations on one idea — minor
variations of the same concept do not count as different). If genuine
evidence only supports fewer than {MIN_SOLUTIONS} distinct approaches,
return only as many as are truly distinct rather than padding with
near-duplicates.

For EACH solution, choose:
  - solution_type: EXACTLY one value from this list, no others:
    [{solution_types_list}]
  - commercial_patterns: one or more values from this list:
    [{patterns_list}]
  - revenue_model: EXACTLY one value from this list:
    [{revenue_list}]
  - estimated_customer_type: EXACTLY one value from this list:
    [{customer_types_list}]

Respond with ONLY a JSON array, no prose, no markdown fences:

[
  {{
    "working_title": "<short name>",
    "solution_type": "<from the list above>",
    "estimated_customer_type": "<from the list above>",
    "target_customer": "<who specifically>",
    "customer_problem": "<restated from the evidence>",
    "value_proposition": "<why this solves it>",
    "commercial_patterns": ["<from the list above>", "..."],
    "revenue_model": "<from the list above>",
    "delivery_model": "<how it reaches the customer>",
    "pricing_strategy": "<approach, not a guessed dollar figure>",
    "automation_potential": "<how much of build/marketing/support can be automated>",
    "estimated_build_complexity": "<Low|Medium|High>",
    "estimated_time_to_mvp": "<rough relative estimate>",
    "required_skills": ["<skill>", "..."],
    "primary_risks": ["<risk>", "..."],
    "key_assumptions": ["<assumption>", "..."],
    "confidence": "<Low|Medium|High>",
    "reasoning": {{
      "why_fits": "<why this solution fits the opportunity>",
      "evidence_support": "<what evidence supports it>",
      "unverified_assumptions": "<what remains unverified>",
      "why_alternative": "<why this is a genuinely different approach from the others generated>"
    }}
  }}
]
"""


def _call_model(model_service, prompt: str, model: str) -> str:
    """Same confirmed contract as ai_scoring.py::_call_model."""
    return model_service.complete(prompt, model=model, options={"temperature": TEMPERATURE})


def _parse_response(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse the model's JSON array of candidate blueprints. Malformed or
    unparseable output degrades to an empty list — same "don't crash
    the run on a bad response" principle as ai_scoring.py, but without a
    per-field Unknown fallback, since a malformed blueprint as a whole
    isn't salvageable the way a single missing score category is.
    """
    try:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        logger.warning("generator: failed to parse model response as JSON")
        return []

    if not isinstance(parsed, list):
        logger.warning("generator: model response was not a JSON array")
        return []

    return [item for item in parsed if isinstance(item, dict)]


def generate_candidates(
    model_service,
    entry: Dict[str, Any],
    model: str = DEFAULT_MODEL,
) -> List[Dict[str, Any]]:
    """
    Single call, one selected opportunity in, a list of raw candidate
    blueprint dicts out (unvalidated — see module docstring). Empty list
    means the model produced nothing usable; the caller (report.py,
    Build Order step 6) decides how that interacts with spec §15's
    Insufficient Commercial Evidence outcome.
    """
    prompt = _build_prompt(entry)
    raw_text = _call_model(model_service, prompt, model=model)
    return _parse_response(raw_text)
