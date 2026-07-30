"""
Complaint extraction — Module 1 step 4 (PHOENIX_ARCHITECTURE.md §3).

Batched `ModelService` calls over collected `RawEvidence`, extracting
candidate complaint statements. Structured output only —
{complaint_text, source_url, source_type, raw_snippet} per item, never
a free-form summary, per the architecture doc.

Decision #5 (approved): batched, never one call per item. Batch size
is configurable for future tuning.

Trust boundary: `source_url`, `source_type`, and `raw_snippet` are
always pulled from the ORIGINAL `RawEvidence` the model was shown —
never taken from the model's own output. The model only ever returns
an `index` (which evidence item) and `complaint_text` (its extraction).
This is deliberate: evidence traceability is non-negotiable per the
architecture doc, so a hallucinated or altered URL/source is
structurally impossible, not just discouraged by prompt wording.

Confirmed against the real `ModelService` contract (same as
source_selector.py): `complete(self, prompt: str, model: str | None =
None, **kwargs) -> str`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from phoenix.collectors.base import RawEvidence

DEFAULT_BATCH_SIZE = 10


@dataclass
class ExtractedComplaint:
    """One extracted complaint, traceable back to its source evidence."""

    complaint_text: str
    source_url: str
    source_type: str
    raw_snippet: str


class ExtractionError(RuntimeError):
    """Raised when a batch's model output can't be parsed or validated."""


def extract_complaints(
    evidence: list[RawEvidence],
    model_service: Any = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[ExtractedComplaint]:
    """Extract complaints from `evidence` in batches of `batch_size`.
    One model call per batch, never per item. Returns a flat list
    across all batches, in no particular guaranteed order relative to
    input beyond within-batch order.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if not evidence:
        return []

    service = model_service if model_service is not None else _get_default_model_service()

    complaints: list[ExtractedComplaint] = []
    for batch in _chunk(evidence, batch_size):
        complaints.extend(_extract_batch(batch, service))
    return complaints


def _get_default_model_service() -> Any:
    from shared_services.registry import get_model_service

    return get_model_service()


def _chunk(items: list[RawEvidence], size: int) -> list[list[RawEvidence]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_prompt(batch: list[RawEvidence]) -> str:
    items_payload = [
        {
            "index": i,
            "text": evidence.raw_snippet,
        }
        for i, evidence in enumerate(batch)
    ]
    items_json = json.dumps(items_payload, indent=2)

    return (
        "You are extracting user complaints from raw public posts for an "
        "evidence-based opportunity discovery report. Below is a JSON "
        "array of evidence items, each with an 'index' and 'text'.\n\n"
        "For each item that contains a genuine complaint (a real "
        "frustration, problem, or pain point expressed by the author — "
        "not a question, not neutral discussion, not praise), extract "
        "it. An item may contain zero, one, or multiple distinct "
        "complaints — include one output element per distinct complaint.\n\n"
        "Respond with ONLY a JSON array, nothing else — no prose, no "
        "markdown fences. Each element must have exactly these two keys:\n"
        '  "index": the source item\'s index (integer, so it can be '
        "matched back to its evidence)\n"
        '  "complaint_text": a concise, factual restatement of the '
        "complaint, in your own words\n\n"
        "Do not invent complaints that aren't actually expressed in the "
        "text. If an item has no genuine complaint, omit it entirely — "
        "do not include an empty or null complaint for it. If no items "
        "contain complaints, return an empty array.\n\n"
        f"Evidence items:\n{items_json}"
    )


def _extract_batch(batch: list[RawEvidence], service: Any) -> list[ExtractedComplaint]:
    prompt = _build_prompt(batch)
    raw_output = service.complete(prompt=prompt)
    parsed_items = _parse_output(raw_output)

    results: list[ExtractedComplaint] = []
    for item in parsed_items:
        idx = item.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(batch):
            raise ExtractionError(f"Model returned an invalid index: {item!r}")

        complaint_text = item.get("complaint_text")
        if not isinstance(complaint_text, str) or not complaint_text.strip():
            raise ExtractionError(f"Model returned an empty complaint_text: {item!r}")

        source = batch[idx]
        results.append(
            ExtractedComplaint(
                complaint_text=complaint_text.strip(),
                source_url=source.source_url,
                source_type=source.source_type,
                raw_snippet=source.raw_snippet,
            )
        )
    return results


def _parse_output(raw_output: str) -> list[dict[str, Any]]:
    text = raw_output.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    if not text:
        return []  # "no complaints in this batch" is a valid outcome

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Model output was not valid JSON: {raw_output!r}") from exc

    if not isinstance(parsed, list):
        raise ExtractionError(f"Expected a JSON array, got: {parsed!r}")

    for item in parsed:
        if not isinstance(item, dict):
            raise ExtractionError(f"Expected a list of objects, got item: {item!r}")

    return parsed
