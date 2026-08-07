"""
phoenix/business_blueprint/validate.py

Business Blueprint Validation — the discrete step between generator.py's
raw per-group output and report.py's persistence call, per spec §9:
"Before persistence the Business Blueprint shall be checked for:
Missing sections, Missing explanations, Duplicate sections, Empty
content, Invalid audit metadata."

Same "is the JSON well-formed" (generator.py's job) vs "is this content
actually valid" (this file's job) split every prior module in this
project uses (Module 4's generator.py/validate.py, Module 5's
validator.py/validate.py). generator.py already raises
SectionGenerationError on malformed JSON — everything reaching this
file is assumed to already be well-formed JSON; this file checks
whether it's a COMPLETE and VALID Business Blueprint.

Three checks, matching the Build Order's own two-pass description
("runs twice — once per group immediately after that group's AI call
... and once again over the fully assembled document before
persistence"):

  1. validate_group_sections() — run immediately after each
     generator.generate_group() call (Build Order Step 8's per-group
     loop), fail fast on a bad group rather than assembling on top of it.
  2. merge_section_results() — the boundary between six independent
     per-group dicts and one flat 17-section document. A section name
     colliding across two groups would otherwise silently overwrite in
     a plain dict merge; this function catches that explicitly, which
     is how "Duplicate sections" (spec §9) is actually detected, since
     categories.BATCH_GROUPS' own disjoint design should make it
     structurally rare — checked, not assumed.
  3. validate_full_document() — the final check over the fully merged
     document before persistence.
  4. validate_audit_metadata() — spec §9's "Invalid audit metadata"
     check, run against the audit dict report.py assembles via audit.py
     (Step 7) before persistence.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from phoenix.business_blueprint import categories

REQUIRED_AUDIT_FIELDS = (
    "module_version",
    "prompt_version",
    "model_version",
    "temperature",
    "audit_hash",
)


def _validate_section_content(section_name: str, section_data: Any, errors: List[str]) -> None:
    """Shared leaf-level check used by both validate_group_sections()
    and validate_full_document() — one place for "what makes a single
    section's content valid," so the two checks can't drift apart."""
    if not isinstance(section_data, dict):
        errors.append(f"{section_name!r}: not a JSON object")
        return

    content = section_data.get("content")
    if not content or not str(content).strip():
        errors.append(f"{section_name!r}: empty or missing content")

    reasoning = section_data.get("reasoning")
    if not reasoning or not str(reasoning).strip():
        errors.append(f"{section_name!r}: empty or missing reasoning (spec §10: every section shall include reasoning)")


def validate_group_sections(group_key: str, sections: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates one group's raw generator.py output — the sections it was
    asked for are exactly the sections it returned (no fewer, no
    unregistered extras), and each has non-empty content and reasoning.

    Returns (is_valid, errors). Does not raise — report.py's
    orchestrator (Step 8) decides how a failed group interacts with the
    rest of the run (SectionGenerationError, retry, or persisting a
    partial version — not this file's decision).
    """
    errors: List[str] = []
    expected = set(categories.sections_for_group(group_key))
    actual = set(sections.keys())

    missing = expected - actual
    if missing:
        errors.append(f"missing section(s) for group {group_key}: {sorted(missing)}")

    unexpected = actual - expected
    if unexpected:
        errors.append(
            f"unexpected section(s) for group {group_key} (not in this group's registry): {sorted(unexpected)}"
        )

    for section_name in sorted(expected & actual):
        _validate_section_content(section_name, sections[section_name], errors)

    return (len(errors) == 0, errors)


def merge_section_results(group_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merges per-group section dicts (one per categories.BATCH_GROUPS
    entry) into one flat 17-section document. This is where "Duplicate
    sections" (spec §9) is actually detected: a plain dict.update() loop
    would silently let a later group's section overwrite an earlier
    one's if the same section name somehow appeared in two groups —
    this function raises instead.

    Args:
        group_results: {group_key: {section_name: {content, reasoning}}, ...}
            — the accumulated output of calling generator.generate_group()
            once per group.

    Returns:
        {section_name: {content, reasoning}, ...} — flat, all groups merged.

    Raises:
        ValueError: if the same section_name appears in more than one
            group's results.
    """
    merged: Dict[str, Any] = {}
    seen_in: Dict[str, str] = {}
    duplicates: List[Tuple[str, str, str]] = []

    for group_key, sections in group_results.items():
        for section_name, section_data in sections.items():
            if section_name in seen_in:
                duplicates.append((section_name, seen_in[section_name], group_key))
                continue
            seen_in[section_name] = group_key
            merged[section_name] = section_data

    if duplicates:
        detail = "; ".join(
            f"{name!r} produced by both group {g1} and group {g2}" for name, g1, g2 in duplicates
        )
        raise ValueError(f"Duplicate section(s) across groups: {detail}")

    return merged


def validate_full_document(all_sections: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates the fully merged document against categories.SECTION_NAMES
    — the final check before persistence. Checks: missing sections,
    unregistered section names, empty content, missing reasoning.
    "Duplicate sections" is already handled by merge_section_results()
    raising before this function would ever see a corrupted merge —
    not re-checked here, since a dict literally cannot hold two values
    under the same key by the time it reaches this function.

    Returns (is_valid, errors). Does not raise — report.py decides
    whether to persist a partial BusinessBlueprintVersion, retry, or
    surface the error, same as every other validate.py in this project.
    """
    errors: List[str] = []
    expected = set(categories.SECTION_NAMES)
    actual = set(all_sections.keys())

    missing = expected - actual
    if missing:
        errors.append(f"missing section(s): {sorted(missing)}")

    unexpected = actual - expected
    if unexpected:
        errors.append(f"unregistered section name(s): {sorted(unexpected)}")

    for section_name in sorted(expected & actual):
        _validate_section_content(section_name, all_sections[section_name], errors)

    return (len(errors) == 0, errors)


def validate_audit_metadata(audit: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Spec §9's "Invalid audit metadata" check — run against the audit
    dict report.py assembles via audit.py (Step 7) before persistence.
    Same required-field shape as every other module's audit block
    (module_version, prompt_version, model_used-equivalent here named
    model_version per BusinessBlueprintVersion's real column name,
    temperature, hash-equivalent here named audit_hash).
    """
    errors: List[str] = []
    for field in REQUIRED_AUDIT_FIELDS:
        if field not in audit or audit[field] in (None, ""):
            errors.append(f"missing or empty audit field: {field}")
    return (len(errors) == 0, errors)


def validate_business_blueprint(
    all_sections: Dict[str, Any], audit: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """
    Convenience wrapper combining validate_full_document() and
    validate_audit_metadata() into the single pre-persistence check
    report.py (Step 8) calls once, over the fully assembled
    BusinessBlueprintVersion candidate.
    """
    doc_valid, doc_errors = validate_full_document(all_sections)
    audit_valid, audit_errors = validate_audit_metadata(audit)
    all_errors = doc_errors + audit_errors
    return (doc_valid and audit_valid, all_errors)
