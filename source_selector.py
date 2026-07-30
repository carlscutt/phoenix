"""
Source selection — the one AI-driven judgement call in Module 1's
pipeline (PHOENIX_ARCHITECTURE.md §3 step 2).

v1 scope: only Reddit is approved as a source (see approved
architecture decisions, #1 and #6), so `SOURCES` is a one-item
registry. Rather than making this a no-op, the ModelService call is
used for what's actually still a judgement call even with one source:
picking concrete starting points (subreddits) relevant to the topic,
per the architecture doc's "ideally concrete starting points
(subreddits, repo search terms, etc.)". Adding a second source later
means extending `SOURCES` and updating the prompt/parsing — nothing
about the call shape changes.

Confirmed against the real contract (shared_services/contracts/
model_service.py): `complete(self, prompt: str, model: str | None =
None, **kwargs) -> str`. `_call_model_service()` below calls
`service.complete(prompt=prompt)`, leaving `model=None` so
OllamaModelService picks its own default — matches the "structured
output only" discipline from the architecture doc (the prompt itself
demands a bare JSON array, parsed and validated below rather than
trusted as-is).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# v1 registry: only Reddit is approved. Extend this list (and the
# prompt below) when a second source is approved — nothing else in
# this module's call shape needs to change.
SOURCES: list[str] = ["reddit"]

DEFAULT_MAX_STARTING_POINTS = 8


@dataclass
class SourceSelection:
    """Structured result of source selection for one topic."""

    topic: str
    sources: list[str]
    starting_points: dict[str, list[str]] = field(default_factory=dict)


class SourceSelectionError(RuntimeError):
    """Raised when the model call fails or returns output that can't
    be parsed into a valid source selection."""


def select_sources(
    topic: str,
    model_service: Any = None,
    max_starting_points: int = DEFAULT_MAX_STARTING_POINTS,
) -> SourceSelection:
    """Given a topic, return the sources to use (v1: always `SOURCES`)
    plus AI-suggested concrete starting points per source.

    `model_service` is injectable for testing — pass a fake with a
    `.complete()` method. In production, omit it and a real one is
    obtained via `get_model_service()` (see the assumption noted in
    the module docstring — unverified this session).
    """
    if not topic or not topic.strip():
        raise ValueError("topic is required and cannot be empty")
    if max_starting_points < 1:
        raise ValueError("max_starting_points must be at least 1")

    service = model_service if model_service is not None else _get_default_model_service()

    prompt = _build_prompt(topic, max_starting_points)
    raw_output = _call_model_service(service, prompt)
    subreddits = _parse_subreddits(raw_output, max_starting_points)

    return SourceSelection(
        topic=topic,
        sources=list(SOURCES),
        starting_points={"reddit": subreddits},
    )


def _get_default_model_service() -> Any:
    # ASSUMPTION — see module docstring. Import kept local so this
    # module can still be imported (and its pure-logic parts tested)
    # even in an environment where shared_services isn't on the path.
    from shared_services.registry import get_model_service

    return get_model_service()


def _build_prompt(topic: str, max_starting_points: int) -> str:
    return (
        "You are selecting Reddit search starting points for an "
        "evidence-gathering task. Given the topic below, return the "
        f"{max_starting_points} subreddit names (without 'r/') most "
        "likely to contain genuine user complaints related to this "
        "topic. Respond with ONLY a JSON array of lowercase subreddit "
        'name strings, nothing else — e.g. ["recruiting", "jobs"]. '
        "No prose, no explanation, no markdown code fences.\n\n"
        f"Topic: {topic}"
    )


def _call_model_service(service: Any, prompt: str) -> str:
    return service.complete(prompt=prompt)


def _parse_subreddits(raw_output: str, max_starting_points: int) -> list[str]:
    text = raw_output.strip()
    # Tolerate accidental markdown fences even though the prompt asks
    # the model not to use them — cheap defensive parsing.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceSelectionError(
            f"Model output was not valid JSON: {raw_output!r}"
        ) from exc

    if not isinstance(parsed, list):
        raise SourceSelectionError(
            f"Expected a JSON array of subreddit names, got: {parsed!r}"
        )

    subreddits: list[str] = []
    for item in parsed:
        if not isinstance(item, str) or not item.strip():
            raise SourceSelectionError(
                f"Expected a list of non-empty strings, got item: {item!r}"
            )
        # Normalize: strip accidental "r/" prefix, lowercase, dedupe.
        name = item.strip().removeprefix("r/").removeprefix("R/").lower()
        if name not in subreddits:
            subreddits.append(name)

    if not subreddits:
        raise SourceSelectionError("Model returned an empty list of subreddits")

    return subreddits[:max_starting_points]
