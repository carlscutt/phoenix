"""
verify_module6.py — real-data validation suite for Module 6 (Business
Blueprint Engine).

Mirrors validate_module4_suite.py's shape (hardcoded 3-opportunity
suite) rather than verify_module5.py's shape (single opportunity via
CLI args) — Module 6's remaining "full-suite proof" step was scoped as
proving against all 3 seeded opportunities, same discipline as Module
4's own release validation.

For each opportunity, this targets the solution_public_id Module 5's
own comparative_summary named as the strongest candidate — not just
whichever validated blueprint happens to be first — so this proves
against the blueprint the system itself would actually recommend
generating a Business Blueprint for.

Requires: Module 4 (Generate Solution Blueprints) and Module 5
(Validate Solutions) already run for each opportunity. This script does
NOT run them for you — same "never trigger upstream generation as a
side effect of a read" discipline every fetch layer in this project
follows (fetch_entry.py, fetch_blueprints.py, fetch_validated_blueprint.py
all share this). If either hasn't been run for an opportunity, this
script says so for that opportunity and moves on rather than running it
for you.

This calls your local Ollama SIX TIMES per opportunity targeted (one
call per bounded generation group) — up to 18 real model calls across
all 3 seeded opportunities, plus 6 more if you opt into the Step G
versioning re-run check. Confirms before running either.

Run:  python3 verify_module6.py
(from ~/projects/phoenix, or wherever phoenix/ and shared_services/ are
importable — same requirement verify_module5.py had)
"""

from __future__ import annotations

import sys
import sqlite3
import subprocess
import traceback
from pathlib import Path
from typing import Any, Dict, List

RUN_ID = 2

# Same three seeded opportunities used throughout Modules 4 and 5's own
# ad-hoc verification.
OPPORTUNITIES = [
    (16, "Recruiters ghost candidates after the first call"),
    (19, "ATS systems reject qualified candidates for keyword mismatches"),
    (21, "Onboarding paperwork is duplicated across three systems"),
]


def _step(name: str) -> None:
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")


def _ok(msg: str) -> None:
    print(f"  PASS — {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL — {msg}")


def main() -> int:
    # ------------------------------------------------------------------
    # Step A — imports (also triggers business_blueprint's init_db()
    # re-run via models.py, so this is also the table-creation step)
    # ------------------------------------------------------------------
    _step("Step A — Import Module 6 package (creates tables if missing)")
    try:
        from phoenix.business_blueprint import (
            models as bb_models,  # noqa: F401
            categories,
            report as bb_report,
        )
        from phoenix.business_blueprint.exceptions import (
            ValidatedBlueprintNotFoundError,
            SolutionNotFoundError,
            SectionGenerationError,
        )
        _ok("phoenix.business_blueprint imported cleanly")
    except Exception as exc:
        _fail(f"import error: {exc!r}")
        print("\nCannot continue past Step A — fix the import error above first.")
        return 1

    # ------------------------------------------------------------------
    # Step B — confirm the two new tables actually exist in phoenix.db
    # ------------------------------------------------------------------
    _step("Step B — Confirm new tables exist in phoenix.db")
    try:
        from phoenix.db import DB_PATH

        conn = sqlite3.connect(str(DB_PATH))
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        expected = {"phoenix_business_blueprint_versions", "phoenix_business_blueprint_sections"}
        missing = expected - tables
        if missing:
            _fail(f"missing table(s): {missing}")
        else:
            _ok(f"both tables present: {sorted(expected)}")
    except Exception as exc:
        _fail(f"could not inspect phoenix.db: {exc!r}")

    # ------------------------------------------------------------------
    # Step C — regression: existing phoenix/tests/ suite must still be
    # fully green (56/56 as of this writing) with ZERO changes needed.
    # ------------------------------------------------------------------
    _step("Step C — Regression: run existing phoenix/tests/ suite")
    tests_dir = Path("phoenix/tests")
    if tests_dir.exists():
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(tests_dir), "-q"],
            capture_output=True,
            text=True,
        )
        print(result.stdout[-2000:])
        if result.returncode == 0:
            _ok("existing test suite passed with no changes needed")
        else:
            _fail("existing test suite reported failures — see output above")
    else:
        print("  SKIPPED — no phoenix/tests/ directory found from this working directory")

    # ------------------------------------------------------------------
    # Step D — for each opportunity, locate a validated blueprint to
    # target, preferring Module 5's own strongest_candidate
    # ------------------------------------------------------------------
    _step("Step D — Locate a validated blueprint per opportunity (Modules 4+5 must already have run)")
    targets: Dict[int, str] = {}
    for cluster_id, expected_problem in OPPORTUNITIES:
        try:
            from phoenix.commercial_validation.report import get_active_validations

            active = get_active_validations(RUN_ID, cluster_id)
            if active is None or not active.get("validated_blueprints"):
                _fail(
                    f"cluster {cluster_id} (\"{expected_problem}\"): no active validation found. "
                    f"Run Module 4 (Generate Solution Blueprints) and Module 5 (Validate Solutions) "
                    f"for this opportunity first, then re-run this script."
                )
                continue

            strongest = active.get("comparative_summary", {}).get("strongest_candidate")
            candidate_id = strongest or active["validated_blueprints"][0]["solution_public_id"]
            targets[cluster_id] = candidate_id
            source = "strongest candidate per Module 5" if strongest else "first validated blueprint (no strongest_candidate set)"
            _ok(f"cluster {cluster_id}: targeting solution_public_id={candidate_id!r} ({source})")
        except Exception:
            _fail(f"cluster {cluster_id}: exception while locating a validated blueprint:\n{traceback.format_exc()}")

    if not targets:
        print(
            "\nNo opportunities have a validated blueprint to target — nothing further to test. "
            "Run Modules 4 and 5 for at least one seeded opportunity, then re-run this script."
        )
        return 1

    # ------------------------------------------------------------------
    # Step E — the real, expensive part: generate a full Business
    # Blueprint (6 real Ollama calls) for each targeted opportunity
    # ------------------------------------------------------------------
    _step("Step E — Generate a full Business Blueprint per opportunity (REAL Ollama, 6 calls each)")
    print(
        f"\nThis will call your local Ollama model 6 times PER opportunity "
        f"({len(targets)} opportunit{'y' if len(targets) == 1 else 'ies'} targeted, "
        f"up to {len(targets) * 6} real model calls total) and PERSIST a new "
        f"BusinessBlueprintVersion for each."
    )
    confirm = input("Continue? [y/N] ").strip().lower()
    if confirm != "y":
        print("  SKIPPED by user.")
        return 0

    suite_results: List[Dict[str, Any]] = []

    for cluster_id, solution_public_id in targets.items():
        print(f"\n--- cluster {cluster_id}, solution_public_id={solution_public_id} ---")
        try:
            result = bb_report.generate_business_blueprint(RUN_ID, cluster_id, solution_public_id)
            _ok(
                f"blueprint_version={result['blueprint_version']}, "
                f"{len(result['sections'])} sections, "
                f"audit_hash={result['audit']['audit_hash'][:16]}..."
            )
            for section_name in categories.SECTION_NAMES:
                section = result["sections"].get(section_name, {})
                content_preview = (section.get("content") or "")[:80]
                print(f"    [{section_name}] {content_preview}...")
            suite_results.append(
                {
                    "cluster_id": cluster_id,
                    "solution_public_id": solution_public_id,
                    "status": "Generated",
                    "result": result,
                }
            )
        except (ValidatedBlueprintNotFoundError, SolutionNotFoundError) as exc:
            _fail(f"cluster {cluster_id}: {exc}")
            suite_results.append({"cluster_id": cluster_id, "status": "NOT_FOUND"})
        except SectionGenerationError as exc:
            _fail(f"cluster {cluster_id}: Business Blueprint Validation failed: {exc}")
            suite_results.append({"cluster_id": cluster_id, "status": "VALIDATION_FAILED"})
        except Exception:
            _fail(f"cluster {cluster_id}: unexpected exception:\n{traceback.format_exc()}")
            suite_results.append({"cluster_id": cluster_id, "status": "EXCEPTION"})

    # ------------------------------------------------------------------
    # Step F — round-trip check: get_active_blueprint() must return
    # exactly what was just persisted, read back from the real database
    # ------------------------------------------------------------------
    _step("Step F — get_active_blueprint() round-trip check (real DB read-back)")
    for entry in suite_results:
        if entry["status"] != "Generated":
            continue
        cluster_id = entry["cluster_id"]
        solution_public_id = entry["solution_public_id"]
        try:
            active = bb_report.get_active_blueprint(solution_public_id)
            if active is None:
                _fail(f"cluster {cluster_id}: get_active_blueprint() returned None right after a successful generation")
                continue
            if set(active["sections"].keys()) != set(categories.SECTION_NAMES):
                _fail(f"cluster {cluster_id}: read-back section set doesn't match SECTION_NAMES")
                continue
            _ok(f"cluster {cluster_id}: read back {len(active['sections'])} sections from the database, all present")
        except Exception:
            _fail(f"cluster {cluster_id}: exception during round-trip check:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Step G — versioning re-run check, ONE opportunity only (not all 3
    # — that would double the real-model-call cost; the mechanism's
    # correctness was already proven exhaustively in sandbox testing,
    # this is a spot-check against real data and real timing, not a
    # from-scratch proof)
    # ------------------------------------------------------------------
    _step("Step G — Versioning re-run check (one opportunity, real Ollama again)")
    generated_entries = [e for e in suite_results if e["status"] == "Generated"]
    if not generated_entries:
        print("  SKIPPED — no successful generation to re-run against.")
    else:
        first_entry = generated_entries[0]
        cluster_id = first_entry["cluster_id"]
        solution_public_id = first_entry["solution_public_id"]
        confirm = input(
            f"\nRe-generate the Business Blueprint for cluster {cluster_id} "
            f"({solution_public_id}) to confirm versioning increments correctly? "
            f"6 more real Ollama calls. [y/N] "
        ).strip().lower()
        if confirm != "y":
            print("  SKIPPED by user.")
        else:
            try:
                second = bb_report.generate_business_blueprint(RUN_ID, cluster_id, solution_public_id)
                expected_version = first_entry["result"]["blueprint_version"] + 1
                if second["blueprint_version"] == expected_version:
                    _ok(f"blueprint_version went {first_entry['result']['blueprint_version']} -> {second['blueprint_version']}")
                else:
                    _fail(f"expected blueprint_version={expected_version}, got {second['blueprint_version']}")

                versions = bb_report.list_blueprint_versions(solution_public_id)
                active_versions = [v for v in versions if v["is_active"]]
                if len(active_versions) == 1 and versions[-1]["is_active"]:
                    _ok(f"exactly one active version ({versions[-1]['blueprint_version']}), all prior versions correctly deactivated")
                else:
                    _fail(f"expected exactly one active version (the newest) — got: {versions}")
            except Exception:
                _fail(f"unexpected error during re-generation:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    _step("SUITE SUMMARY")
    generated_count = sum(1 for e in suite_results if e["status"] == "Generated")
    not_found_count = sum(1 for e in suite_results if e["status"] == "NOT_FOUND")
    validation_failed_count = sum(1 for e in suite_results if e["status"] == "VALIDATION_FAILED")
    exception_count = sum(1 for e in suite_results if e["status"] == "EXCEPTION")

    print(f"Opportunities targeted: {len(targets)}")
    print(
        f"  Generated: {generated_count}  |  Not found (M4/M5 not run): {not_found_count}  |  "
        f"Validation failed: {validation_failed_count}  |  Exceptions: {exception_count}"
    )
    print("\nPaste this entire output back — I'll assess it against a release recommendation for Module 6.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
