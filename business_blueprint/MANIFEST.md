# Module 6 — Step 8 Delivery Manifest
Build Order Step 8: `report.py` — the orchestrator. Also includes a
third, final correction to `models.py` that this step's design surfaced.

## Files → destination

| Delivered as | Place at |
|---|---|
| `DEST_phoenix_business_blueprint_models.py` | `projects/phoenix/business_blueprint/models.py` (**overwrites**, see below) |
| `DEST_phoenix_business_blueprint_report.py` | `projects/phoenix/business_blueprint/report.py` |

## One more `models.py` correction — why, and why it's safe

Writing `report.py`'s versioning logic surfaced a real gap: the
`BusinessBlueprintVersion` model had no version-number column at all —
every other module's version table has one
(`generation_version`/`validation_version`/`scoring_version`), this one
didn't. Added `blueprint_version` (integer, matches the same pattern).

Safe to change now, not a migration: no `BusinessBlueprintVersion` row
has ever been persisted (Step 8, the first thing that could write one,
didn't exist until this delivery). If you've been running the
`python3 -c "import phoenix.business_blueprint.models"` sanity check
periodically, that's fine — it only ever created empty tables, never
inserted a row.

## What `report.py` does

Three functions:
- `generate_business_blueprint(run_id, cluster_id, solution_public_id, model)` —
  runs all six bounded groups, validates each and the assembled whole,
  computes the audit hash, persists, deactivates the prior active
  version.
- `get_active_blueprint(solution_public_id)` — read-only, `None` if
  nothing generated yet.
- `list_blueprint_versions(solution_public_id)` — read-only, full
  history.

Two things worth knowing about, both confirmed against your real
`solution_generation/report.py` and `commercial_validation/report.py`
(I checked, not guessed, this time):

1. **`correlation_id` is `str(cluster_id)`, not a minted UUID.** I'd
   been assuming Module 6 would need to mint its own since Module 5 has
   nothing to inherit — turns out neither Module 4 nor Module 5
   persists a `correlation_id` column at all; both only ever use
   `str(cluster_id)` as a per-log-call parameter to `LoggingService`.
   Module 6 does the same, and also stores it on the row for the Studio
   UI to display later.
2. **Atomic rollback comes for free.** The version-number lookup,
   prior-version deactivation, and final validation all happen inside
   one `get_session()` block, in that order — validation runs *before*
   `prior_active.is_active = False` is even set, and if it fails, the
   whole block raises before any write happens. If a later group fails
   after an earlier group's deactivation logic ran... actually it can't:
   deactivation only happens after ALL groups are generated and
   validated. Confirmed by the third real test below — a failing group
   leaves the database completely untouched, not partially written.

## Actually verified — the big one

Three real tests, chaining the full pipeline (`generate_solutions()` →
`validate_solutions()` → `generate_business_blueprint()`, all real code,
real Module 4/5 source):

1. **Full real chain, all 6 groups** — a `FakeModelService` that
   inspects each prompt to figure out which group it's for and returns
   that group's real sections. Confirmed: all 17 sections present with
   real content/reasoning; audit hash present; exactly 6 model calls (no
   more, no fewer); `get_active_blueprint()` round-trips correctly from
   the database; `correlation_id` is `str(cluster_id)`; **re-generating
   creates version 2 and correctly deactivates version 1**;
   `list_blueprint_versions()` shows both with correct `is_active` states
   in the right order.
2. **Raises `ValidatedBlueprintNotFoundError`** when called before
   Module 5 has validated the opportunity — nothing persisted.
3. **A malformed group response raises and rolls back completely** —
   confirmed via `get_active_blueprint()` returning `None` and
   `list_blueprint_versions()` returning empty afterward, i.e. nothing
   was left half-written.

All 3 passed. Full 23-test baseline re-confirmed clean after.

## Where Module 6's backend stands now

All 8 Build Order steps are done and individually proven against real
Module 4/5 code. What's left, per the Build Order's own final steps:

- **Full-suite proof** — generate real Business Blueprints for all
  three seeded opportunities (not just cluster 16), on your actual
  machine, with real Ollama — same "prove against real data" step every
  module has done before being called done.
- **Dashboard/Studio UI** (spec §13) — last, per the standing
  backend-before-UI rule.
- **Release paperwork** — Release Notes, Handoff, Git Tag, Freeze, same
  shape as Modules 4 and 5.

Want me to draft the full-suite real-data proof script next (mirroring
`verify_module5.py`'s shape, since this is genuinely new code that
hasn't touched your actual Ollama/DB yet), or go straight to the Studio
UI?
