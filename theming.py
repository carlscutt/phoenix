"""
Thematic grouping — Module 2, PHOENIX_MODULE2_ARCHITECTURE.md.

Groups Module 1's ComplaintClusters into 5-10 business themes (approved
decision, 2026-07-25) — semantic, AI-driven grouping layered on top of
Module 1's already-deduplicated clusters. Never touches raw evidence or
complaints directly; only cluster-level data (representative_text,
occurrence_count, source_diversity) already assembled by an existing
OpportunityReport. See models.py's Module 2 docstring section for why
this is versioned (ThemeVersion/OpportunityTheme/
ThemeClusterAssignment) rather than a flat FK on ComplaintCluster.

Two-phase design. Both phases confirmed against the real ModelService
contract (complete(self, prompt, model=None, **kwargs) -> str, same as
source_selector.py and extraction.py):

  Phase 1 — candidate labeling (batched, scales WITH cluster count).
  Each batch of `batch_size` clusters gets a short free-text candidate
  theme label per cluster. Mirrors extraction.py's batching discipline
  exactly: one call per batch, never per-cluster. Satisfies the
  approved "batched processing continues throughout" decision for the
  part of this problem that actually scales with run size.

  Phase 2 — consolidation (a single call that scales with the number
  of DISTINCT candidate labels from phase 1, NOT with cluster count).
  Candidate labels are deduped and aggregated in Python first, so this
  call stays cheap even on a run with many clusters — it only has to
  reconcile "CV formatting help" and "CV rewriting advice" into one
  canonical theme, not re-read every cluster's full text again. This
  is a single, unbatched call by design: naming a coherent, non-
  overlapping final theme set genuinely requires seeing all candidate
  groups at once — batching this step would mean merging theme names
  across batches after the fact, which is a strictly harder and more
  error-prone problem than reconciling from one bounded view. Cluster
  volume drives phase 1's cost; it does not drive phase 2's.

Same trust boundary as extraction.py: which cluster is which
(position -> representative_text/occurrence_count/source_diversity)
always comes from OUR OWN batch indexing, never from the model's
output. The model only ever returns which index goes with which
label/theme — a label the model invents is just a label, never treated
as a source of truth for what a cluster IS.

Every cluster is guaranteed a theme assignment. If phase 2's parsed
output leaves any cluster unassigned, it falls back into "Other" in
code — never silently dropped, per PHOENIX_MODULE2_ARCHITECTURE.md
§3 step 3's Module 1 precedent.

The "Other" bucket cap (~10%, approved decision) is enforced by
DETECTION here, not by silently discarding the model's answer: the
prompt asks the model to split Other into an extra theme if it would
run over, and `other_bucket_exceeded` is set on the result regardless
so callers (phoenix_actions.py) can log a recommendation per the
approved "if exceeded, recommend creating a new theme" decision — this
module reports the condition, it doesn't retry or force a fix.

Edge case, flagged rather than silently handled: a run with fewer than
MIN_THEMES clusters can't produce MIN_THEMES non-empty themes without
one cluster per theme. `effective_min` relaxes the floor to
`min(MIN_THEMES, len(clusters))` for that case rather than raising —
worth revisiting once real cluster-count distributions are known.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

DEFAULT_BATCH_SIZE = 10
MIN_THEMES = 5
MAX_THEMES = 10
OTHER_BUCKET_CAP_PERCENT = 10.0
OTHER_THEME_NAME = "Other"


@dataclass
class ClusterInput:
    """One ComplaintCluster's data as theming.py needs it. `position` is
    the same 0-based translation convention phoenix_actions.py's
    _persist_results already uses for cluster/complaint wiring —
    theming.py never sees or needs the actual DB id, only this
    position, which the caller maps back to a real ComplaintCluster.id
    after the fact (same trust boundary as extraction.py's `index`).
    """

    position: int
    representative_text: str
    occurrence_count: int
    source_diversity: int


@dataclass
class ThemeGroup:
    """One final theme and the cluster positions assigned to it."""

    theme_name: str
    rationale: str
    cluster_positions: list[int]


@dataclass
class ThemeGenerationResult:
    """Structured result of theming one run's clusters. `other_bucket_
    exceeded` is a detection, not a correction — see module docstring.
    """

    topic: str
    groups: list[ThemeGroup]
    other_bucket_percent: float
    other_bucket_exceeded: bool


class ThemingError(RuntimeError):
    """Raised when a model call's output can't be parsed or validated."""


def group_into_themes(
    clusters: list[ClusterInput],
    topic: str,
    model_service: Any = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ThemeGenerationResult:
    """Group `clusters` into MIN_THEMES-MAX_THEMES business themes plus
    an "Other" catch-all. Two model-call phases — see module docstring.

    `model_service` is injectable for testing — pass a fake with a
    `.complete()` method. In production, omit it and a real one is
    obtained via `get_model_service()`.
    """
    if not topic or not topic.strip():
        raise ValueError("topic is required and cannot be empty")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if not clusters:
        return ThemeGenerationResult(
            topic=topic, groups=[], other_bucket_percent=0.0, other_bucket_exceeded=False
        )

    service = model_service if model_service is not None else _get_default_model_service()

    # Phase 1 — batched candidate labeling (scales with cluster count)
    candidate_labels: dict[int, str] = {}
    for batch in _chunk(clusters, batch_size):
        candidate_labels.update(_label_batch(batch, service))

    # Group clusters by normalized candidate label — free, Python-side.
    label_groups: dict[str, list[int]] = defaultdict(list)
    for position, label in candidate_labels.items():
        label_groups[_normalize_label(label)].append(position)

    # Phase 2 — single consolidation call (scales with distinct labels)
    groups = _consolidate(label_groups, clusters, topic, service)

    # Safety net: every cluster must land somewhere, even if phase 2's
    # parsed output left one out.
    assigned = {p for g in groups for p in g.cluster_positions}
    unassigned = [c.position for c in clusters if c.position not in assigned]
    if unassigned:
        other = next((g for g in groups if g.theme_name == OTHER_THEME_NAME), None)
        if other is None:
            other = ThemeGroup(
                theme_name=OTHER_THEME_NAME,
                rationale="Not confidently grouped by the model.",
                cluster_positions=[],
            )
            groups.append(other)
        other.cluster_positions.extend(unassigned)

    total = len(clusters)
    other_count = sum(len(g.cluster_positions) for g in groups if g.theme_name == OTHER_THEME_NAME)
    other_pct = (other_count / total * 100.0) if total else 0.0

    return ThemeGenerationResult(
        topic=topic,
        groups=groups,
        other_bucket_percent=round(other_pct, 1),
        other_bucket_exceeded=other_pct > OTHER_BUCKET_CAP_PERCENT,
    )


def _get_default_model_service() -> Any:
    from shared_services.registry import get_model_service

    return get_model_service()


def _chunk(items: list[ClusterInput], size: int) -> list[list[ClusterInput]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _normalize_label(label: str) -> str:
    return " ".join(label.strip().lower().split())


# ---------------------------------------------------------------------
# Phase 1 — candidate labeling
# ---------------------------------------------------------------------


def _label_batch(batch: list[ClusterInput], service: Any) -> dict[int, str]:
    prompt = _build_label_prompt(batch)
    raw_output = service.complete(prompt=prompt)
    parsed = _parse_json_array(raw_output, context="phase 1 labeling")

    result: dict[int, str] = {}
    for item in parsed:
        idx = item.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(batch):
            raise ThemingError(f"Model returned an invalid index in phase 1: {item!r}")
        label = item.get("candidate_theme")
        if not isinstance(label, str) or not label.strip():
            raise ThemingError(f"Model returned an empty candidate_theme: {item!r}")
        result[batch[idx].position] = label.strip()

    # Every cluster in the batch must get a label — nothing silently
    # dropped. A cluster the model skipped becomes its own Other
    # candidate rather than vanishing from the run.
    for c in batch:
        result.setdefault(c.position, OTHER_THEME_NAME)
    return result


def _build_label_prompt(batch: list[ClusterInput]) -> str:
    items_payload = [
        {
            "index": i,
            "complaint": c.representative_text,
            "occurrence_count": c.occurrence_count,
        }
        for i, c in enumerate(batch)
    ]
    items_json = json.dumps(items_payload, indent=2)
    return (
        "You are labeling user complaints with a short business-theme "
        "candidate name, as the first pass of a two-pass thematic "
        "grouping. Below is a JSON array of distinct complaints, each "
        "already deduplicated (so each item is a genuinely different "
        "complaint, not a near-duplicate of another item here).\n\n"
        "For each item, suggest a short (2-5 word) candidate business "
        'theme name that captures what business activity or need this '
        'complaint relates to — e.g. "CV rewriting help" or "Cover '
        'Letter Feedback" — not a restatement of the complaint itself. '
        "Similar complaints should tend to get similar or identical "
        "labels, since these labels get merged together in a later "
        "step.\n\n"
        "Respond with ONLY a JSON array, nothing else — no prose, no "
        "markdown fences. Each element must have exactly these two "
        "keys:\n"
        '  "index": the item\'s index (integer)\n'
        '  "candidate_theme": your short label (string)\n\n'
        f"Complaints:\n{items_json}"
    )


# ---------------------------------------------------------------------
# Phase 2 — consolidation
# ---------------------------------------------------------------------


def _consolidate(
    label_groups: dict[str, list[int]],
    clusters: list[ClusterInput],
    topic: str,
    service: Any,
) -> list[ThemeGroup]:
    by_position = {c.position: c for c in clusters}
    total_clusters = len(clusters)

    # One summary row per distinct candidate label — this is what keeps
    # phase 2 cheap regardless of cluster count. One example complaint
    # per group for context, not every cluster's full text.
    candidate_payload = []
    for i, (label, positions) in enumerate(label_groups.items()):
        candidate_payload.append(
            {
                "index": i,
                "label": label,
                "cluster_count": len(positions),
                "example_complaint": by_position[positions[0]].representative_text,
            }
        )

    prompt = _build_consolidation_prompt(topic, candidate_payload, total_clusters)
    raw_output = service.complete(prompt=prompt)
    parsed = _parse_json_array(raw_output, context="phase 2 consolidation")

    groups: list[ThemeGroup] = []
    seen_indices: set[int] = set()
    for theme_obj in parsed:
        theme_name = theme_obj.get("theme_name")
        rationale = theme_obj.get("rationale")
        member_indices = theme_obj.get("member_indices")

        if not isinstance(theme_name, str) or not theme_name.strip():
            raise ThemingError(f"Model returned an invalid theme_name: {theme_obj!r}")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ThemingError(f"Model returned an invalid rationale: {theme_obj!r}")
        if not isinstance(member_indices, list):
            raise ThemingError(f"Model returned invalid member_indices: {theme_obj!r}")
        # An empty list is valid, not an error — most commonly the model
        # correctly found nothing that belongs in "Other" (every cluster
        # fit a named theme). A theme with zero members simply
        # contributes nothing below rather than being force-populated;
        # if that drops named themes below MIN_THEMES, the count check
        # at the end of this function catches that as a real problem.

        positions: list[int] = []
        for idx in member_indices:
            if not isinstance(idx, int) or idx < 0 or idx >= len(candidate_payload):
                raise ThemingError(f"Model returned an invalid member index: {idx!r}")
            if idx in seen_indices:
                # A candidate group the model assigned to more than one
                # final theme — keep the first assignment, never
                # double-count a cluster across two themes.
                continue
            seen_indices.add(idx)
            positions.extend(label_groups[candidate_payload[idx]["label"]])

        if positions:
            groups.append(
                ThemeGroup(
                    theme_name=theme_name.strip(), rationale=rationale.strip(), cluster_positions=positions
                )
            )

    named_themes = [g for g in groups if g.theme_name != OTHER_THEME_NAME]
    # Bounded by distinct candidate groups, not raw cluster count — you
    # can't produce more non-overlapping named themes than there are
    # candidate label groups to draw from, regardless of how many
    # clusters those groups collectively cover.
    effective_min = min(MIN_THEMES, len(candidate_payload))
    if not (effective_min <= len(named_themes) <= MAX_THEMES):
        raise ThemingError(
            f"Expected {effective_min}-{MAX_THEMES} named themes, model produced "
            f"{len(named_themes)}: {[g.theme_name for g in named_themes]}"
        )

    return groups


def _build_consolidation_prompt(
    topic: str, candidate_payload: list[dict[str, Any]], total_clusters: int
) -> str:
    payload_json = json.dumps(candidate_payload, indent=2)
    return (
        f"You are consolidating candidate complaint labels for the topic "
        f"'{topic}' into a final set of business themes for an "
        "evidence-based opportunity report. Below is a JSON array of "
        "candidate label groups — each already-similar complaints that "
        "got the same or a near-identical short label in a first pass. "
        f"Merge these into a final set of {MIN_THEMES}-{MAX_THEMES} named "
        "business themes.\n\n"
        "Prefer more specific, narrower themes over fewer broad umbrella "
        'ones. For example, "Process Inefficiencies" covering both '
        "interview scheduling delays and reference-check delays is too "
        "broad if those are genuinely different complaints — split it "
        'into "Interview Scheduling Delays" and "Reference Check '
        'Delays" instead. If your first attempt produces fewer than '
        f"{MIN_THEMES} themes, go back and split your broadest group(s) "
        f"into more specific ones until you reach at least {MIN_THEMES} "
        "— do not submit fewer than that unless there are genuinely "
        f"fewer than {MIN_THEMES} candidate label groups below to work "
        "with in the first place.\n\n"
        'Include one additional theme named exactly "Other" for '
        "candidate groups that genuinely don't fit any clear business "
        'theme. Keep "Other" small — if it would end up covering more '
        f"than roughly {int(OTHER_BUCKET_CAP_PERCENT)}% of the "
        f"{total_clusters} total complaints, split it into an "
        "additional named theme instead of letting it grow.\n\n"
        "Respond with ONLY a JSON array, nothing else — no prose, no "
        "markdown fences. Each element must have exactly these three "
        "keys:\n"
        '  "theme_name": short business theme name (string, "Other" for '
        "the catch-all)\n"
        '  "rationale": one sentence on why these complaints belong '
        "together (string)\n"
        '  "member_indices": the candidate group "index" values (from '
        "the input below) that belong to this theme (array of "
        "integers)\n\n"
        "Every candidate group index must appear in exactly one theme's "
        "member_indices.\n\n"
        f"Candidate label groups:\n{payload_json}"
    )


def _parse_json_array(raw_output: str, context: str) -> list[dict[str, Any]]:
    text = raw_output.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    if not text:
        raise ThemingError(f"Model returned empty output during {context}")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ThemingError(
            f"Model output during {context} was not valid JSON: {raw_output!r}"
        ) from exc

    if not isinstance(parsed, list):
        raise ThemingError(f"Expected a JSON array during {context}, got: {parsed!r}")
    for item in parsed:
        if not isinstance(item, dict):
            raise ThemingError(f"Expected a list of objects during {context}, got item: {item!r}")
    return parsed
