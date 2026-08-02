"""
phoenix/commercial_validation/validator.py

The AI call for Module 5: evaluates ONE SolutionBlueprint independently
against the nine spec §8 scoring categories and produces a
recommendation. Called once per blueprint by report.py's orchestration
loop.

Comparative Validation Rule (Carl, approved with the Build Order): this
module NEVER compares multiple blueprints against each other, and the
prompt below shows the model exactly one business concept with no
reference to any sibling. Comparative ranking happens exclusively in
report.py, after every blueprint in the set has already been scored
independently here — deterministic, no AI call, fully explainable.

Future-Proofing Rule: this file is one scoring *contributor*, not the
whole engine. validate_blueprint() returns a plain dict of AI-produced
scores; report.py owns assembling the final ValidatedSolutionBlueprint.
Future deterministic sources (SEO metrics, pricing APIs, search volume,
competition intelligence, trend analysis — spec §20) plug in as
additional functions called from report.py alongside this one, without
changing this file's signature or the public ValidationVersion contract.

NOTE ON VERIFICATION: written to the ModelService.complete(prompt,
model=None, **kwargs) contract as documented from Modules 3/4
(temperature passed via an options dict, model pinned explicitly) — not
re-executed against the live registry in this session (no real
ModelService/Ollama available here). Per the Build Order's own "prove
before continuing" discipline, run this against one real blueprint
before relying on Step 6 (validate.py) or Step 8 (report.py) — if the
real ModelService signature differs from what's assumed here, this is
the one function that needs adjusting; nothing downstream should.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from phoenix.commercial_validation.categories import RECOMMENDATIONS, CONFIDENCE_LEVELS

PROMPT_VERSION = "phoenix-module5-validator-v1"
TEMPERATURE = 0.0  # deterministic scoring — same reasoning as Module 4's TEMPERATURE=0.0
DEFAULT_MODEL: Optional[str] = None  # resolved by ModelService's own default unless the caller overrides it

SCORE_FIELDS: List[str] = [
    "market_need_score",
    "customer_pain_score",
    "revenue_potential_score",
    "competition_score",
    "technical_complexity_score",
    "time_to_mvp_score",
    "founder_fit_score",
    "ai_leverage_score",
    "defensibility_score",
]


def _build_prompt(blueprint: Dict[str, Any], problem_statement: str, supporting_evidence_refs: list) -> str:
    """
    Single-blueprint prompt. Deliberately contains no reference to any
    sibling blueprint — Comparative Validation Rule: comparison never
    happens here, only in report.py's orchestration after every
    blueprint has already been scored independently.
    """
    return f"""You are the Commercial Validation Engine for an evidence-driven
internet business operating system. Evaluate exactly ONE business
concept below. You are not shown any other concepts, and there are none
to compare against here — evaluate this concept entirely on its own
merits.

Problem Statement (from the underlying validated opportunity):
{problem_statement}

Business Concept:
- Working Title: {blueprint.get('working_title')}
- Solution Type: {blueprint.get('solution_type')}
- Target Customer: {blueprint.get('target_customer')} ({blueprint.get('estimated_customer_type')})
- Customer Problem: {blueprint.get('customer_problem')}
- Value Proposition: {blueprint.get('value_proposition')}
- Commercial Patterns: {blueprint.get('commercial_patterns')}
- Revenue Model: {blueprint.get('revenue_model')}
- Delivery Model: {blueprint.get('delivery_model')}
- Pricing Strategy: {blueprint.get('pricing_strategy')}
- Automation Potential: {blueprint.get('automation_potential')}
- Estimated Build Complexity: {blueprint.get('estimated_build_complexity')}
- Estimated Time To MVP: {blueprint.get('estimated_time_to_mvp')}
- Required Skills: {blueprint.get('required_skills')}
- Primary Risks (from generation): {blueprint.get('primary_risks')}
- Key Assumptions (from generation): {blueprint.get('key_assumptions')}

Score this concept on each of the following axes, as an integer 0-100
(0 = worst, 100 = best). Do not invent market evidence, customer
behaviour, or financial forecasts beyond what you were given above —
where evidence is thin, score conservatively and say so in the
explanation (spec §12: "The AI must not invent market evidence").

- market_need_score
- customer_pain_score
- revenue_potential_score
- competition_score (higher = LESS saturated / more Blue Ocean)
- technical_complexity_score (higher = LOWER complexity, i.e. easier to build)
- time_to_mvp_score (higher = FASTER to reach a usable MVP)
- founder_fit_score (fit against a solo builder skilled in: AI Automation, Python, Business Systems, Infrastructure, Operations, Documentation, Automation)
- ai_leverage_score (higher = more of the MVP can realistically be AI-accelerated)
- defensibility_score (network effects, brand, data advantage, community, automation, unique assets)

Then choose exactly one overall_recommendation from this closed list —
do not invent a different label:
{RECOMMENDATIONS}

And exactly one validation_confidence from this closed list — reflects
evidence quality only, never predicts success:
{CONFIDENCE_LEVELS}

Respond with ONLY a single JSON object, no other text, no markdown
fences, in exactly this shape:

{{
  "market_need_score": <int>,
  "customer_pain_score": <int>,
  "revenue_potential_score": <int>,
  "competition_score": <int>,
  "technical_complexity_score": <int>,
  "time_to_mvp_score": <int>,
  "founder_fit_score": <int>,
  "ai_leverage_score": <int>,
  "defensibility_score": <int>,
  "overall_recommendation": "<one of the closed list above, verbatim>",
  "validation_confidence": "<one of the closed list above, verbatim>",
  "validation_explanation": "<2-4 sentences: why this scored as it did>",
  "strengths": ["<short phrase>", "..."],
  "weaknesses": ["<short phrase>", "..."],
  "primary_risks": ["<short phrase>", "..."],
  "suggested_improvements": ["<short phrase>", "..."]
}}
"""


def validate_blueprint(
    model_service: Any,
    blueprint: Dict[str, Any],
    problem_statement: str,
    supporting_evidence_refs: list,
    model: Optional[str] = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    Runs one independent AI validation call for one blueprint. Returns
    the parsed dict as-is — NOT yet checked against categories.py or
    range-checked, that's validate.py's job (Validation Output
    Validation), called separately by report.py before persistence.

    Raises ValueError if the model's response isn't valid JSON. The
    caller (report.py) treats that the same way Module 4's own
    validate_candidates() treats a bad candidate: skipped, logged, not
    coerced into looking valid.
    """
    prompt = _build_prompt(blueprint, problem_statement, supporting_evidence_refs)
    response = model_service.complete(
        prompt,
        model=model,
        options={"temperature": TEMPERATURE},
    )
    text = response.strip() if isinstance(response, str) else str(response).strip()

    # Defensive: strip markdown fences if the model adds them despite
    # the "no markdown fences" instruction above.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Validator response was not valid JSON: {exc}\nRaw response: {text[:500]}")

    return parsed
