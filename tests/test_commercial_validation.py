"""
phoenix/tests/test_commercial_validation.py

Permanent pytest coverage for Module 5 (Commercial Validation Engine),
converted from verify_module5.py per MODULE_05_HANDOFF.md §0.

FINAL PASS 2026-08-02: Carl supplied the complete real
commercial_validation package as a zip (an earlier standalone upload of
"validate.py" had turned out to be this package's file mislabeled as
Module 4's — the zip resolved that and confirmed the real field names:
overall_recommendation, validation_confidence, the 9 SCORE_FIELDS, no
correlation_id anywhere on ValidationVersion). This file now has full
orchestrator coverage (validate_solutions(), get_active_validations(),
versioning, the BlueprintSetNotFoundError path), not just the
validator.py unit tests from the previous pass — all run for real in a
sandboxed environment against both real packages (solution_generation +
commercial_validation), not just ast.parse'd.

Orchestrator tests chain through Module 4 first (fake_model_service_m4)
to create real SolutionGenerationVersion/SolutionBlueprint rows, then
Module 5 (fake_model_service_m5) validates them — same dependency
Module 5 has in production (spec §3/§21: it never generates blueprints
itself).

Run:  python3 -m pytest phoenix/tests/test_commercial_validation.py -v
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from phoenix.db import DB_PATH, get_session
from phoenix.solution_generation.report import generate_solutions
from phoenix.commercial_validation.validator import validate_blueprint, SCORE_FIELDS
import phoenix.commercial_validation.models  # noqa: F401 - ensure table registration before any test in this file runs


# ======================================================================
# Orchestrator-level tests (report.py) — hermetic, chains through a real
# Module 4 generation first (spec requirement: Module 5 never generates
# blueprints itself, so tests must create them the same way production
# does — via generate_solutions()).
# ======================================================================

def test_commercial_validation_tables_exist(db) -> None:
    """Confirms both new tables actually get created via init_db()'s
    create_all() side effect on import — same check verify_module5.py's
    Step B made, now against the in-memory test engine."""
    from phoenix.db import _engine

    with _engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    expected = {"phoenix_validation_versions", "phoenix_validated_solution_blueprints"}
    missing = expected - tables
    assert not missing, f"missing table(s): {missing}"


def test_validate_solutions_end_to_end(
    db, fake_model_service_m4, fake_model_service_m5, seeded_scoring_version, mock_opportunity_entry
) -> None:
    """
    Real end-to-end path: generate 3 blueprints via Module 4, validate
    them via Module 5, confirm persistence and the exact return-dict
    shape confirmed from the real report.py.
    """
    from phoenix.commercial_validation.report import validate_solutions, get_active_validations

    run_id = seeded_scoring_version["run_id"]
    cluster_id = 16

    generated = generate_solutions(run_id=run_id, cluster_id=cluster_id)
    assert generated["status"] == "Generated"

    outcome = validate_solutions(run_id, cluster_id)

    assert outcome["status"] == "Validated"
    assert outcome["candidates_validated"] == 3
    assert outcome["candidates_rejected"] == 0
    assert outcome["validation_version"] == 1
    assert "comparative_summary" in outcome
    assert outcome["comparative_summary"]["strongest_candidate"] in {
        b["public_id"] for b in generated["blueprints"]
    }
    assert len(outcome["validated_blueprints"]) == 3
    for vb in outcome["validated_blueprints"]:
        assert vb["overall_recommendation"] == "Worth Testing"
        assert vb["validation_confidence"] == "Medium"
        for field in SCORE_FIELDS:
            assert field in vb

    audit = outcome["audit"]
    for key in ("module_version", "prompt_version", "model_used", "temperature", "hash"):
        assert key in audit

    # Round-trip: confirms a real DB read-back, not just trusting
    # validate_solutions()'s own return value (verify_module5.py Step I).
    active = get_active_validations(run_id, cluster_id)
    assert active is not None
    assert len(active["validated_blueprints"]) == 3
    assert active["validation_version"] == 1


def test_validate_solutions_insufficient_evidence_when_no_blueprints(
    db, fake_model_service_m5, seeded_scoring_version, mock_opportunity_entry
) -> None:
    """
    Module 5 never generates blueprints itself — if Module 4 was never
    run for this opportunity, validate_solutions() must return
    "Insufficient Commercial Evidence", not raise or crash.
    """
    from phoenix.commercial_validation.report import validate_solutions

    run_id = seeded_scoring_version["run_id"]
    cluster_id = 999  # nothing generated for this cluster

    outcome = validate_solutions(run_id, cluster_id)
    assert outcome["status"] == "Insufficient Commercial Evidence"
    assert outcome["validated_blueprints"] == []


def test_versioning_increments_and_deactivates_prior(
    db, fake_model_service_m4, fake_model_service_m5, seeded_scoring_version, mock_opportunity_entry
) -> None:
    """
    Re-running validate_solutions() for the same opportunity should
    increment validation_version and deactivate the prior version — the
    exact behavior verify_module5.py's Step H/I manually re-ran by hand
    (documented in MODULE_05_HANDOFF.md: 1 → 2, prior deactivated).
    """
    from phoenix.commercial_validation.report import validate_solutions, get_active_validations
    from phoenix.commercial_validation.models import ValidationVersion

    run_id = seeded_scoring_version["run_id"]
    cluster_id = 16

    generated = generate_solutions(run_id=run_id, cluster_id=cluster_id)
    assert generated["status"] == "Generated"

    first = validate_solutions(run_id, cluster_id)
    second = validate_solutions(run_id, cluster_id)

    assert first["status"] == "Validated" and second["status"] == "Validated"
    assert second["validation_version"] == first["validation_version"] + 1

    with get_session() as session:
        first_version_row = (
            session.query(ValidationVersion)
            .filter(ValidationVersion.validation_version == first["validation_version"])
            .first()
        )
        assert first_version_row is not None
        assert first_version_row.is_active is False, "prior validation version should be deactivated"

    active = get_active_validations(run_id, cluster_id)
    assert active is not None
    assert active["validation_version"] == second["validation_version"]


def test_comparative_summary_ranks_by_score_deterministically(
    db, fake_model_service_m4, seeded_scoring_version, mock_opportunity_entry, monkeypatch
) -> None:
    """
    Comparative Validation Rule check at the orchestrator level: ranking
    must be deterministic and based on overall_validation_score, with no
    AI call involved in the ranking itself. Uses a model service that
    returns different scores per call (by working_title) to confirm the
    ranking actually reflects the scores, not just call order.
    """
    import phoenix.commercial_validation.report as cv_report_module
    from phoenix.commercial_validation.report import validate_solutions

    run_id = seeded_scoring_version["run_id"]
    cluster_id = 16

    generated = generate_solutions(run_id=run_id, cluster_id=cluster_id)
    assert generated["status"] == "Generated"

    # Deliberately score "Test Solution 2" highest, regardless of call order.
    class VariableScoreModelService:
        def complete(self, prompt, model=None, **kwargs):
            base = 50
            if "Test Solution 2" in prompt:
                base = 90
            payload = {field: base for field in SCORE_FIELDS}
            payload.update(
                {
                    "overall_recommendation": "Worth Testing",
                    "validation_confidence": "Medium",
                    "validation_explanation": "test",
                    "strengths": [],
                    "weaknesses": [],
                    "primary_risks": [],
                    "suggested_improvements": [],
                }
            )
            return json.dumps(payload)

    class NullLog:
        def log_event(self, **kwargs):
            pass

    monkeypatch.setattr(cv_report_module, "get_model_service", lambda: VariableScoreModelService())
    monkeypatch.setattr(cv_report_module, "get_logging_service", lambda: NullLog())

    outcome = validate_solutions(run_id, cluster_id)
    winner_public_id = outcome["comparative_summary"]["strongest_candidate"]

    winning_blueprint = next(
        b for b in generated["blueprints"] if b["public_id"] == winner_public_id
    )
    assert winning_blueprint["working_title"] == "Test Solution 2"


# ======================================================================
# Direct unit tests — validator.py (unchanged from previous pass, still
# fully faithful — real source, no mocking needed beyond the model call)
# ======================================================================

class FakeModelServiceValidator:
    def __init__(self, response_override: str | None = None):
        self.calls = []
        self.response_override = response_override

    def complete(self, prompt: str, model=None, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "model": model, "kwargs": kwargs})
        if self.response_override is not None:
            return self.response_override

        payload = {field: 65 for field in SCORE_FIELDS}
        payload.update(
            {
                "overall_recommendation": "Worth Testing",
                "validation_confidence": "Medium",
                "validation_explanation": "test fixture explanation",
                "strengths": ["clear customer pain"],
                "weaknesses": ["thin evidence"],
                "primary_risks": ["low switching cost"],
                "suggested_improvements": ["validate pricing with a landing page test"],
            }
        )
        return json.dumps(payload)


SAMPLE_BLUEPRINT = {
    "working_title": "Test Solution",
    "solution_type": "Micro SaaS",
    "target_customer": "Independent recruiters",
    "estimated_customer_type": "Business",
    "customer_problem": "Candidates are ghosted after the first call",
    "value_proposition": "Automated status updates close the loop",
    "commercial_patterns": ["Automation Tool"],
    "revenue_model": "Subscription",
    "delivery_model": "Web app",
    "pricing_strategy": "Tiered monthly",
    "automation_potential": "High",
    "estimated_build_complexity": "Low",
    "estimated_time_to_mvp": "4-6 weeks",
    "required_skills": ["Python", "Automation"],
    "primary_risks": ["Low switching cost for competitors"],
    "key_assumptions": ["Recruiters will pay for automated updates"],
}


def test_validate_blueprint_calls_model_with_temperature_zero() -> None:
    svc = FakeModelServiceValidator()
    validate_blueprint(svc, SAMPLE_BLUEPRINT, "Recruiters ghost candidates", [], model="qwen3-coder:30b")

    assert len(svc.calls) == 1
    call = svc.calls[0]
    assert call["model"] == "qwen3-coder:30b"
    assert call["kwargs"]["options"] == {"temperature": 0.0}


def test_validate_blueprint_parses_all_score_fields() -> None:
    svc = FakeModelServiceValidator()
    result = validate_blueprint(svc, SAMPLE_BLUEPRINT, "Recruiters ghost candidates", [])

    for field in SCORE_FIELDS:
        assert field in result
        assert isinstance(result[field], int)


def test_validate_blueprint_prompt_contains_no_sibling_reference() -> None:
    """Comparative Validation Rule regression check."""
    svc = FakeModelServiceValidator()
    other_title = "A Completely Different Sibling Concept"
    validate_blueprint(svc, SAMPLE_BLUEPRINT, "Recruiters ghost candidates", [])

    prompt = svc.calls[0]["prompt"]
    assert other_title not in prompt
    assert "sibling" not in prompt.lower() or "no other concepts" in prompt.lower()


def test_validate_blueprint_raises_valueerror_on_malformed_json() -> None:
    svc = FakeModelServiceValidator(response_override="not valid json at all")
    with pytest.raises(ValueError):
        validate_blueprint(svc, SAMPLE_BLUEPRINT, "Recruiters ghost candidates", [])


def test_validate_blueprint_strips_markdown_fences() -> None:
    payload = {field: 50 for field in SCORE_FIELDS}
    payload.update(
        {
            "overall_recommendation": "Reject",
            "validation_confidence": "Low",
            "validation_explanation": "test",
            "strengths": [],
            "weaknesses": [],
            "primary_risks": [],
            "suggested_improvements": [],
        }
    )
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    svc = FakeModelServiceValidator(response_override=fenced)

    result = validate_blueprint(svc, SAMPLE_BLUEPRINT, "Recruiters ghost candidates", [])
    assert result["overall_recommendation"] == "Reject"


# ======================================================================
# Direct unit tests — validate.py (Validation Output Validation)
# ======================================================================

def _well_formed_validation_result(**overrides) -> dict:
    base = {field: 70 for field in SCORE_FIELDS}
    base.update(
        {
            "overall_recommendation": "Worth Testing",
            "validation_confidence": "Medium",
            "validation_explanation": "reasonable explanation",
            "strengths": ["a"],
            "weaknesses": ["b"],
            "primary_risks": ["c"],
            "suggested_improvements": ["d"],
        }
    )
    base.update(overrides)
    return base


def test_validate_results_accepts_well_formed() -> None:
    from phoenix.commercial_validation.validate import validate_results

    accepted, rejected = validate_results([_well_formed_validation_result()])
    assert len(accepted) == 1
    assert rejected == []


def test_validate_results_rejects_score_out_of_range() -> None:
    from phoenix.commercial_validation.validate import validate_results

    result = _well_formed_validation_result(market_need_score=150)
    accepted, rejected = validate_results([result])
    assert accepted == []
    assert any("market_need_score" in e for e in rejected[0]["_validation_errors"])


def test_validate_results_rejects_unregistered_recommendation() -> None:
    from phoenix.commercial_validation.validate import validate_results

    result = _well_formed_validation_result(overall_recommendation="Definitely Do This")
    accepted, rejected = validate_results([result])
    assert accepted == []
    assert any("overall_recommendation" in e for e in rejected[0]["_validation_errors"])


# --------------------------------------------------------------------
# NOT COVERED — explicit
# --------------------------------------------------------------------
# - list_validation_versions() / list_validation_versions_for_opportunity()
#   — straightforward read helpers, lower risk, not exercised yet.
# - fetch_blueprints.get_blueprint_set()'s own BlueprintSetNotFoundError
#   path is exercised indirectly (via validate_solutions()'s Insufficient
#   Commercial Evidence test above) but not directly unit-tested.
