"""
phoenix/tests/test_solution_generation.py

Hermetic pytest coverage for Module 4 (Solution Generation Engine),
converted from validate_module4_suite.py per MODULE_05_HANDOFF.md §0.

FINAL PASS 2026-08-02: Carl supplied the complete real
solution_generation package as a zip (resolving an earlier mix-up where
a standalone "validate.py" upload turned out to be Module 5's file, not
Module 4's — the zip confirmed the content used to build these tests
matches the real file exactly). All 10 tests below were run for real —
not just ast.parse'd — in a sandboxed environment using the real
solution_generation package, with stubs only for what's genuinely
unconfirmed this session (phoenix/scoring/models.py's full schema,
phoenix/models.py's exact real definition). All 10 pass.

mock_opportunity_entry now lives in conftest.py (shared with
test_commercial_validation.py, which needs Module 4 blueprints to exist
before it can validate them).

Run:  python3 -m pytest phoenix/tests/test_solution_generation.py -v
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from phoenix.db import get_session
from phoenix.scoring.models import ScoringVersion
from phoenix.solution_generation.models import SolutionGenerationVersion, SolutionBlueprint
from phoenix.solution_generation.report import generate_solutions, get_active_solutions


# ======================================================================
# Orchestrator-level tests (report.py) — hermetic, get_opportunity_entry
# mocked (conftest.py's mock_opportunity_entry), everything else real
# ======================================================================

def test_generate_solutions_persists_correctly(
    db, fake_model_service_m4, seeded_scoring_version, mock_opportunity_entry
) -> None:
    """
    Core check the original ad-hoc script existed to make: does what
    generate_solutions() returns actually match what landed in the
    database, independently re-queried (not trusted from the return
    value)? Runs hermetically — FakeModelServiceM4 stands in for Ollama,
    in-memory DB stands in for phoenix.db.
    """
    run_id = seeded_scoring_version["run_id"]
    cluster_id = 16  # arbitrary — get_opportunity_entry is fully mocked

    result = generate_solutions(run_id=run_id, cluster_id=cluster_id)

    assert result["status"] == "Generated"
    assert len(result["blueprints"]) == 3

    with get_session() as session:
        scoring_version_row = (
            session.query(ScoringVersion)
            .filter(
                ScoringVersion.phoenix_run_id == run_id,
                ScoringVersion.scoring_version == result["scoring_version"],
            )
            .first()
        )
        assert scoring_version_row is not None, "parent ScoringVersion not found"

        gen_version_row = (
            session.query(SolutionGenerationVersion)
            .filter(
                SolutionGenerationVersion.scoring_version_id == scoring_version_row.id,
                SolutionGenerationVersion.cluster_id == cluster_id,
                SolutionGenerationVersion.generation_version == result["generation_version"],
            )
            .first()
        )
        assert gen_version_row is not None, "SolutionGenerationVersion row not found"
        assert gen_version_row.is_active, "persisted version is not marked active"

        blueprint_rows = (
            session.query(SolutionBlueprint)
            .filter(SolutionBlueprint.solution_generation_version_id == gen_version_row.id)
            .all()
        )
        persisted_ids = {b.public_id for b in blueprint_rows}
        returned_ids = {b["public_id"] for b in result["blueprints"]}
        assert persisted_ids == returned_ids, (
            f"DB has {persisted_ids}, returned dict had {returned_ids}"
        )

        for b in result["blueprints"]:
            assert b["public_id"].startswith("SBP-")
            assert b["confidence"] in ("Low", "Medium", "High")


def test_module5_contract_extension_present(
    db, fake_model_service_m4, seeded_scoring_version, mock_opportunity_entry
) -> None:
    """
    Confirms the Step 0 Module 5 extension is actually in the code under
    test: get_active_solutions() must return problem_statement /
    supporting_evidence_refs / audit.
    """
    run_id = seeded_scoring_version["run_id"]
    cluster_id = 16

    result = generate_solutions(run_id=run_id, cluster_id=cluster_id)
    assert result["status"] == "Generated"

    active = get_active_solutions(run_id, cluster_id)
    assert active is not None

    for key in ("problem_statement", "supporting_evidence_refs", "audit"):
        assert key in active, f"missing key {key!r} on get_active_solutions() result"

    audit = active["audit"]
    for key in ("module_version", "prompt_version", "model_used", "temperature", "hash"):
        assert key in audit


def test_versioning_deactivates_prior_version(
    db, fake_model_service_m4, seeded_scoring_version, mock_opportunity_entry
) -> None:
    """
    Re-running generate_solutions() for the same opportunity should
    deactivate the prior SolutionGenerationVersion.
    """
    run_id = seeded_scoring_version["run_id"]
    cluster_id = 16

    first = generate_solutions(run_id=run_id, cluster_id=cluster_id)
    assert first["status"] == "Generated"

    second = generate_solutions(run_id=run_id, cluster_id=cluster_id)
    assert second["status"] == "Generated"
    assert second["generation_version"] == first["generation_version"] + 1

    with get_session() as session:
        first_row = (
            session.query(SolutionGenerationVersion)
            .filter(
                SolutionGenerationVersion.cluster_id == cluster_id,
                SolutionGenerationVersion.generation_version == first["generation_version"],
            )
            .first()
        )
        assert first_row is not None and first_row.is_active is False, (
            "prior version should be deactivated once a new one is generated"
        )


# ======================================================================
# Direct unit tests — validate.py (Blueprint Validation)
# ======================================================================

def _well_formed_candidate(**overrides) -> Dict[str, Any]:
    base = {
        "working_title": "Recruiter Status Bot",
        "solution_type": "Micro SaaS",
        "estimated_customer_type": "Business",
        "target_customer": "Independent recruiters",
        "customer_problem": "Candidates are ghosted after the first call",
        "value_proposition": "Automated status updates close the loop",
        "commercial_patterns": ["Subscription"],
        "revenue_model": "Subscription",
        "delivery_model": "Web app",
        "pricing_strategy": "Tiered monthly",
        "automation_potential": "High",
        "estimated_build_complexity": "Low",
        "estimated_time_to_mvp": "4-6 weeks",
        "required_skills": ["Python"],
        "primary_risks": ["Low switching cost"],
        "key_assumptions": ["Recruiters will pay"],
        "confidence": "Medium",
        "reasoning": {
            "why_fits": "fits",
            "evidence_support": "supported",
            "unverified_assumptions": "none major",
            "why_alternative": "different approach",
        },
    }
    base.update(overrides)
    return base


def test_validate_candidates_accepts_well_formed() -> None:
    from phoenix.solution_generation.validate import validate_candidates

    accepted, rejected = validate_candidates([_well_formed_candidate()])
    assert len(accepted) == 1
    assert rejected == []


def test_validate_candidates_rejects_missing_required_field() -> None:
    from phoenix.solution_generation.validate import validate_candidates

    candidate = _well_formed_candidate()
    del candidate["pricing_strategy"]

    accepted, rejected = validate_candidates([candidate])
    assert accepted == []
    assert len(rejected) == 1
    assert "pricing_strategy" in rejected[0]["reason"]


def test_validate_candidates_rejects_unregistered_solution_type() -> None:
    from phoenix.solution_generation.validate import validate_candidates

    candidate = _well_formed_candidate(solution_type="Blockchain NFT Platform")

    accepted, rejected = validate_candidates([candidate])
    assert accepted == []
    assert "not in registry" in rejected[0]["reason"]


def test_validate_candidates_rejects_duplicate_value_proposition() -> None:
    """
    The exact bug FakeModelServiceM4's fixture originally tripped over —
    locked in as a permanent regression test now that it's understood.
    """
    from phoenix.solution_generation.validate import validate_candidates

    first = _well_formed_candidate(working_title="A", solution_type="Micro SaaS")
    second = _well_formed_candidate(working_title="B", solution_type="API")

    accepted, rejected = validate_candidates([first, second])
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "duplicate within this run"


def test_validate_candidates_rejects_invalid_confidence() -> None:
    from phoenix.solution_generation.validate import validate_candidates

    candidate = _well_formed_candidate(confidence="Very High")

    accepted, rejected = validate_candidates([candidate])
    assert accepted == []
    assert "confidence" in rejected[0]["reason"]


# ======================================================================
# Direct unit tests — fetch_entry.py
# ======================================================================

def test_get_opportunity_entry_raises_when_cluster_not_found(monkeypatch) -> None:
    from phoenix.solution_generation.fetch_entry import get_opportunity_entry
    from phoenix.solution_generation.exceptions import OpportunityEntryNotFoundError
    import phoenix.solution_generation.fetch_entry as fetch_entry_module

    fake_report = {
        "scoring_version": 1,
        "audit": {},
        "entries": [{"opportunity_id": 999, "status": "Scored"}],
    }
    monkeypatch.setattr(fetch_entry_module, "get_score_report", lambda run_id, sv=None: fake_report)

    with pytest.raises(OpportunityEntryNotFoundError):
        get_opportunity_entry(run_id=1, cluster_id=16)


def test_get_opportunity_entry_returns_matching_entry(monkeypatch) -> None:
    from phoenix.solution_generation.fetch_entry import get_opportunity_entry
    import phoenix.solution_generation.fetch_entry as fetch_entry_module

    fake_report = {
        "scoring_version": 1,
        "audit": {"hash": "abc"},
        "entries": [{"opportunity_id": 16, "status": "Scored", "overall_score": 70}],
    }
    monkeypatch.setattr(fetch_entry_module, "get_score_report", lambda run_id, sv=None: fake_report)

    result = get_opportunity_entry(run_id=1, cluster_id=16)
    assert result["entry"]["opportunity_id"] == 16
    assert result["audit"] == {"hash": "abc"}
    assert result["run_id"] == 1
    assert result["scoring_version"] == 1


# --------------------------------------------------------------------
# NOTE — read before extending
# --------------------------------------------------------------------
# Not covered here, and why: solution diversity across multiple
# opportunities (the original script's suite-wide check) isn't
# meaningful against one FakeModelService returning the same 3 canned
# candidates every time — that was a real-model-quality observation,
# not something a hermetic unit test should assert on. If you want that
# check kept as a permanent (slow, real-Ollama) test, it belongs in a
# separately marked file/marker (e.g. @pytest.mark.live), not mixed into
# this hermetic suite.
#
# get_opportunity_entry() is still mocked at the orchestrator-test level
# — Module 3's real audit-block shape (phoenix/scoring/report.py) still
# isn't confirmed this session. The two direct unit tests above exercise
# fetch_entry.py's own real logic in isolation instead, which doesn't
# need that.
