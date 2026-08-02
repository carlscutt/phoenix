# Module 5 Implementation — Delivery Manifest

All files below are **complete files**, ready to overwrite the destination path directly — no find/replace anywhere in this delivery, per your standing rule.

Filenames are prefixed `DEST_` + the destination path with `/` replaced by `_`, so there's no ambiguity about where each one goes. Strip the `DEST_` prefix conceptually — it's not part of the real filename.

| Delivered as | Destination path | Build Order step |
|---|---|---|
| `DEST_phoenix_solution_generation_report.py` | `phoenix/solution_generation/report.py` | **Step 0** — Module 4 extension |
| `DEST_phoenix_commercial_validation___init__.py` | `projects/phoenix/commercial_validation/__init__.py` | new package |
| `DEST_phoenix_commercial_validation_models.py` | `projects/phoenix/commercial_validation/models.py` | Step 1 |
| `DEST_phoenix_commercial_validation_categories.py` | `projects/phoenix/commercial_validation/categories.py` | Step 2 |
| `DEST_phoenix_commercial_validation_fetch_blueprints.py` | `projects/phoenix/commercial_validation/fetch_blueprints.py` | Step 3 |
| `DEST_phoenix_commercial_validation_exceptions.py` | `projects/phoenix/commercial_validation/exceptions.py` | Step 4 |
| `DEST_phoenix_commercial_validation_validator.py` | `projects/phoenix/commercial_validation/validator.py` | Step 5 |
| `DEST_phoenix_commercial_validation_validate.py` | `projects/phoenix/commercial_validation/validate.py` | Step 6 |
| `DEST_phoenix_commercial_validation_audit.py` | `projects/phoenix/commercial_validation/audit.py` | Step 7 |
| `DEST_phoenix_commercial_validation_report.py` | `projects/phoenix/commercial_validation/report.py` | Step 8 (orchestrator) |

**Not included in this delivery, per the approved Build Order:** `phoenix_actions.py` additions, `routes.py` additions, and the Studio UI section (Steps 9-10). Those come after Step 0-8 are placed and you've verified the extended Module 4 contract and the new engine against real data — same "backend proven before UI" discipline Module 4 itself used.

---

## What I could and couldn't verify from this sandbox

I have **no live phoenix package, no real phoenix.db, no ModelService/Ollama, and no shared_services registry** available here — this session only has the static files you uploaded. So "verification" in this delivery means:

- **Done:** every file above passed `python3 -m py_compile` (syntax-valid, no typos, no indentation errors).
- **Done:** cross-checked import paths, class names, and field names against the real files you provided (`models.py`, `report.py`, `patterns.py`, `db.py`) rather than guessed.
- **Not done, and can't be from here:** an actual run against your real database, your real ModelService, or your real `SolutionGenerationVersion` rows. That has to happen on your machine.

**Please run Step 0 (the extended `report.py`) against one real, already-generated opportunity first** — re-run `get_active_solutions()` on existing data and confirm `problem_statement`, `supporting_evidence_refs`, and `audit` now come back populated, and confirm your existing `phoenix/tests/` regression suite (33/33 baseline) still passes with no changes needed. That's the "prove Step 0 before continuing" checkpoint the Build Order called for — per your Freeze Rule, once that's confirmed, Module 4 goes back to frozen and nothing here should touch it again without a genuine defect.

Then run `phoenix/commercial_validation/validator.py`'s `validate_blueprint()` against one real blueprint before trusting Steps 6-8 — this is the one function most likely to need adjustment if the real `ModelService.complete()` signature differs from what Modules 3/4 documented it as.

---

## Design decisions made during implementation, flagged rather than silently baked in

1. **problem_statement / supporting_evidence_refs are opportunity-level**, returned once at the top of the blueprint-set dict, not duplicated onto every blueprint (they're the same value for every blueprint in one generation run either way).
2. **Score range is 0-100 per §8 category, and `overall_validation_score` is an unweighted mean of the nine.** MODULE_05_SPECIFICATION.md gives no explicit range or weights (unlike Module 3, which specified exact percentage weights). This is the most defensible default until you supply real weights — the formula lives in exactly one place (`report.py::_overall_score`) if you want to change it later.
3. **`get_active_validations()`'s generation-version lookup takes the newest `SolutionGenerationVersion` for a `cluster_id`** rather than resolving through a specific `scoring_version` — because `get_active_solutions()`'s return shape doesn't carry `scoring_version_id`, and adding it would mean touching Module 4 a second time. Correct for the normal case; flagged in the code if a cluster ever legitimately has multiple active generations under different scoring versions.
4. **`validate_solutions()` does not fall back to calling Module 4's `generate_solutions()`** if nothing's been generated yet — it raises/returns "Insufficient Commercial Evidence" instead, keeping Module 5 strictly evaluation-only per spec §3 and §21.
