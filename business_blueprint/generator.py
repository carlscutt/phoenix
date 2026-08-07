"""
phoenix/business_blueprint/generator.py

The AI call for Module 6: generates content for ONE bounded group of
sections at a time (categories.BATCH_GROUPS), grounded in the validated
business concept fetched by fetch_validated_blueprint.py. Called once
per group by report.py's orchestration loop (Build Order Step 8) — six
calls per full Business Blueprint generation, never one giant unbounded
call, per Decision 1 (approved with the Build Order).

Per Build Order Step 5: this file proves Group A alone (Executive
Summary, Customer Definition, Problem Definition) first — the other
five groups (B-F) reuse this exact same function, parameterized by
group_key, so there is no per-group code to duplicate. Group A was
chosen as the first proof because it's the most self-contained (no
dependency on numbers or technical detail that later groups need to be
consistent with).

Model-call contract copied directly from the confirmed real pattern in
phoenix/solution_generation/generator.py and phoenix/commercial_validation/
validator.py — not re-derived or guessed:
  - ModelService.complete(prompt, model=None, **kwargs) — temperature
    goes through Ollama's own options dict: options={"temperature": TEMPERATURE}.
  - model is passed explicitly so the model actually used is pinned and
    auditable (spec §8: "Model Version" is a required audit field).
  - JSON response parsing: strip markdown fences if present, then
    json.loads.

Where this file's error handling differs from Module 4's generator.py
and matches Module 5's validator.py instead: a malformed or unparseable
response RAISES (SectionGenerationError), it does not silently degrade
to an empty result. Module 4's generator.py degrades to an empty
candidate list because losing one candidate among 3-5 is recoverable —
Blueprint Validation (a separate, later step) just sees fewer
candidates. Here, a Business Blueprint with a missing group is a hole
in the document, not a smaller-but-still-valid set — same reasoning
Module 5's validator.py already applied to raise ValueError on a single
blueprint's malformed response. report.py (Step 8) decides how a raised
SectionGenerationError interacts with persisting a partial
BusinessBlueprintVersion; this file's only job is "did the model
produce usable JSON for exactly this group's sections."

This file does NOT check for missing sections, empty content, or
missing reasoning within an otherwise-valid JSON response — that is
Business Blueprint Validation (validate.py, Build Order Step 6),
deliberately a separate step, same "is the JSON well-formed" vs "is
this section-set actually valid" split every prior module in this
project has used (Module 4's generator.py/validate.py,
Module 5's validator.py/validate.py).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from phoenix.business_blueprint import categories
from phoenix.business_blueprint.exceptions import SectionGenerationError

logger = logging.getLogger(__name__)

PROMPT_VERSION = "phoenix-module6-business-blueprint-v1"
TEMPERATURE = 0.0  # same determinism rationale as generator.py/validator.py (Decision 3-equivalent)

# Matches the DEFAULT_MODEL pattern in solution_generation/generator.py —
# kept as its own constant (not imported from another module) since
# Module 6's model choice is its own audited decision, per spec §8.
DEFAULT_MODEL = "qwen3-coder:30b"  # CONFIRM WITH CARL, same flag every prior module's generator raised


def _build_prompt(group_key: str, fetched: Dict[str, Any]) -> str:
    """
    fetched is the dict returned by fetch_validated_blueprint.get_validated_blueprint()
    — solution_blueprint (Module 4's content), validated_blueprint
    (Module 5's scores/recommendation), problem_statement.

    Deliberately contains ONLY this group's target sections — never the
    full 17-section list, and never another group's content — keeping
    each call bounded, per Decision 1. Unlike Module 5's Comparative
    Validation Rule (which exists to prevent comparing sibling
    business concepts), the boundary here is scope, not comparison:
    nothing stops group B's prompt from also describing the same
    business concept — it just never asks for or receives another
    group's section content.
    """
    sections = categories.sections_for_group(group_key)
    solution = fetched["solution_blueprint"]
    validated = fetched["validated_blueprint"]

    sections_list = "\n".join(f'  - "{s}"' for s in sections)

    return f"""You are writing part of an implementation-ready Business Blueprint
for a validated business concept. A founder — or a future autonomous
system — should be able to act directly on what you write.

Use ONLY the information given below. Do not invent market data,
revenue figures, customer counts, or competitors not implied by the
material given. Where evidence is insufficient to support a specific
claim, explicitly say so and state it as an assumption rather than
presenting it as fact (spec requirement: no unsupported claims).

Validated Business Concept:
  Working Title: {solution.get('working_title')}
  Solution Type: {solution.get('solution_type')}
  Target Customer: {solution.get('target_customer')} ({solution.get('estimated_customer_type')})
  Customer Problem: {solution.get('customer_problem')}
  Value Proposition: {solution.get('value_proposition')}
  Revenue Model: {solution.get('revenue_model')}
  Commercial Patterns: {solution.get('commercial_patterns')}
  Delivery Model: {solution.get('delivery_model')}
  Pricing Strategy: {solution.get('pricing_strategy')}
  Estimated Build Complexity: {solution.get('estimated_build_complexity')}
  Estimated Time To MVP: {solution.get('estimated_time_to_mvp')}
  Required Skills: {solution.get('required_skills')}

Underlying Opportunity:
  Problem Statement: {fetched.get('problem_statement')}

Commercial Validation (independent assessment, already completed):
  Recommendation: {validated.get('overall_recommendation')}
  Confidence: {validated.get('validation_confidence')}
  Overall Score: {validated.get('overall_validation_score')}
  Strengths: {validated.get('strengths')}
  Weaknesses: {validated.get('weaknesses')}
  Primary Risks: {validated.get('primary_risks')}
  Suggested Improvements: {validated.get('suggested_improvements')}

Produce content for EXACTLY these sections — no more, no fewer, no
other sections, and use these exact names as JSON keys:
{sections_list}

For each section: write grounded, specific, implementation-ready
content, and a short explanation of your reasoning — why this content
follows from the validated concept above, specifically for that
section (spec requirement: every section shall include reasoning, and
every recommendation shall reference the validated business).

Keep each section's "content" to roughly 100-150 words, and each
"reasoning" to 1-2 sentences. Concise and complete beats long and
truncated — a shorter response you finish is far more useful than a
longer one that gets cut off mid-sentence.

Respond with ONLY a single JSON object, no other text, no markdown
fences, in exactly this shape:

{{
  "<exact section name from the list above>": {{
    "content": "<the section's full content>",
    "reasoning": "<why this content follows from the validated concept>"
  }}
}}
"""


def _call_model(model_service: Any, prompt: str, model: Optional[str]) -> str:
    """Same confirmed contract as generator.py/validator.py."""
    return model_service.complete(prompt, model=model, options={"temperature": TEMPERATURE})


def _parse_response(raw_text: str) -> Dict[str, Any]:
    """
    Parse the model's JSON object of {section_name: {content, reasoning}}.
    Raises SectionGenerationError on malformed/unparseable output — see
    module docstring for why this raises rather than degrading to an
    empty result, unlike Module 4's generator.py.
    """
    text = raw_text.strip() if isinstance(raw_text, str) else str(raw_text).strip()

    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SectionGenerationError(
            f"Group response was not valid JSON: {exc}\nRaw response: {text[:500]}"
        )

    if not isinstance(parsed, dict):
        raise SectionGenerationError(
            f"Group response was not a JSON object (got {type(parsed).__name__})"
        )

    return parsed


def generate_group(
    model_service: Any,
    group_key: str,
    fetched: Dict[str, Any],
    model: Optional[str] = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    Runs one bounded AI call for one group (categories.BATCH_GROUPS,
    'A' through 'F'). Returns the parsed {section_name: {content,
    reasoning}} dict as-is — NOT yet checked for missing sections,
    empty content, or missing reasoning fields; that's
    validate.py's job (Business Blueprint Validation, Build Order
    Step 6), called separately by report.py before persistence.

    Raises:
        ValueError: if group_key isn't a real group (from
            categories.sections_for_group()).
        SectionGenerationError: if the model's response isn't valid
            JSON, or isn't a JSON object.
    """
    prompt = _build_prompt(group_key, fetched)
    raw_text = _call_model(model_service, prompt, model=model)
    return _parse_response(raw_text)
