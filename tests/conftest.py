"""
Corrected 2026-07-28, second pass — against Carl's real shared_services
package:

  - There is no set_model_service() in the real shared_services/registry.py
    — it's @lru_cache-wrapped and always constructs a real
    OllamaModelService(). Test injection now works by monkeypatching the
    `get_model_service`/`get_logging_service` names as imported INTO
    phoenix.scoring.report (not the registry module itself), via
    pytest's `monkeypatch` fixture. This is the standard pattern for
    swapping a dependency that a real registry doesn't expose a seam
    for, and it doesn't touch shared_services at all.

  - FakeModelService.complete() now matches the real ModelService
    contract: complete(self, prompt, model=None, **kwargs) — accepts
    `model` and an `options` dict (Ollama's own temperature/num_ctx
    passthrough), not a `temperature` kwarg directly.

  - init_engine_for_tests() never existed in the real phoenix/db.py — it
    was a sandbox-only stub. The real db.py binds to a literal phoenix.db
    file at import time (module-level _engine/_SessionLocal), so test
    isolation requires monkeypatching those two module attributes to an
    in-memory engine BEFORE any test creates a session — done in the
    `db` fixture below via `_use_in_memory_db()`.

  - seeded_run sets ComplaintCluster.occurrence_count and
    .source_diversity directly (matching real field names), since
    report.py reads those fields from the cluster row itself rather
    than recounting Complaint children.

--------------------------------------------------------------------
2026-08-02 additions — Module 4 + Module 5 fixtures
--------------------------------------------------------------------
Added for phoenix/tests/test_solution_generation.py and
test_commercial_validation.py, per MODULE_05_HANDOFF.md §0's pytest
conversion.

Both FakeModelServiceM4 and FakeModelServiceM5 were checked against the
real solution_generation/{patterns,validate}.py and
commercial_validation/{models,categories}.py respectively (Carl
supplied both full packages as zips), and actually executed end-to-end
in a sandboxed stub environment (real phoenix.solution_generation and
phoenix.commercial_validation packages, stubbed phoenix.db/models/
scoring — the one piece genuinely not available this session) —
not just ast.parse'd. All 10 test_solution_generation.py cases and the
full test_commercial_validation.py orchestrator suite pass against
real code with these fixtures.

FakeModelServiceM4's 3 canned candidates use registered patterns.py
values and distinct value_propositions per candidate (an earlier
version used an unregistered pattern and identical
value_propositions across all 3 — both real bugs, caught and fixed
against the real validate.py/patterns.py, not guessed).

FakeModelServiceM5's canned response field names (overall_recommendation,
validation_confidence, SCORE_FIELDS) are confirmed directly against the
real commercial_validation/models.py and categories.py — no longer
inferred, unlike earlier passes this session.
"""
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import phoenix.db as db_module
import phoenix.scoring.report as report_module
from phoenix.models import Base, PhoenixRun, ComplaintCluster, Complaint, ThemeVersion, OpportunityTheme, ThemeClusterAssignment


class FakeModelService:
    """
    Returns a canned, well-formed JSON array response for every batch —
    lets tests exercise the full pipeline without a real Ollama call.
    Matches the real ModelService.complete(prompt, model=None, **kwargs)
    signature.
    """

    def __init__(self):
        self.calls = []
        self.next_response = None  # if set, used for the next .complete() call

    def complete(self, prompt: str, model: str | None = None, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "model": model, "kwargs": kwargs})
        if self.next_response is not None:
            resp = self.next_response
            self.next_response = None
            return resp

        import re
        ids = [int(m) for m in re.findall(r"cluster_id: (\d+)", prompt)]
        return json.dumps(
            [
                {
                    "cluster_id": cid,
                    "severity": 60,
                    "market_demand": 50,
                    "revenue_potential": 55,
                    "competition_saturation": 40,
                    "automation_potential": 70,
                    "time_to_first_revenue": 65,
                    "reasoning": "test fixture response",
                }
                for cid in ids
            ]
        )


class NullLoggingService:
    def log_event(self, **kwargs):
        pass

    def log_error(self, **kwargs):
        pass

    def record_metric(self, **kwargs):
        pass

    def get_history(self, **kwargs):
        return []


def _use_in_memory_db():
    """
    Swap phoenix.db's module-level engine/session factory for an
    in-memory sqlite instance, so tests never touch the real phoenix.db
    file. Safe because get_session() looks up _SessionLocal from module
    scope at call time, so reassigning it here takes effect immediately
    for every subsequent `with get_session()` in the test.
    """
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db_module._engine = test_engine
    db_module._SessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=test_engine)


@pytest.fixture()
def db():
    _use_in_memory_db()
    yield


@pytest.fixture()
def fake_model_service(monkeypatch):
    svc = FakeModelService()
    monkeypatch.setattr(report_module, "get_model_service", lambda: svc)
    monkeypatch.setattr(report_module, "get_logging_service", lambda: NullLoggingService())
    return svc


@pytest.fixture()
def seeded_run(db):
    """One PhoenixRun with three clusters: well-evidenced, thin, empty."""
    from phoenix.db import get_session

    with get_session() as session:
        run = PhoenixRun(topic="recruitment")
        session.add(run)
        session.flush()

        rich = ComplaintCluster(
            phoenix_run_id=run.id,
            representative_text="Scheduling interviews across time zones is a mess",
            occurrence_count=6,
            source_diversity=2,
        )
        thin = ComplaintCluster(
            phoenix_run_id=run.id,
            representative_text="Candidate ghosting after offer",
            occurrence_count=1,
            source_diversity=1,
        )
        empty = ComplaintCluster(
            phoenix_run_id=run.id,
            representative_text="Payroll export formatting",
            occurrence_count=0,
            source_diversity=0,
        )
        session.add_all([rich, thin, empty])
        session.flush()

        for i in range(6):
            session.add(
                Complaint(
                    phoenix_run_id=run.id,
                    cluster_id=rich.id,
                    complaint_text=f"Recruiter complaint {i} about scheduling across time zones",
                    source_url=f"https://reddit.com/r/recruiting/{i}",
                    source_type="reddit" if i % 2 == 0 else "github",
                )
            )
        session.add(
            Complaint(
                phoenix_run_id=run.id,
                cluster_id=thin.id,
                complaint_text="One candidate ghosted after signing",
                source_url="https://reddit.com/r/recruiting/99",
                source_type="reddit",
            )
        )
        # `empty` gets zero complaints and occurrence_count=0 on purpose
        # — Insufficient Evidence case.

        return {"run_id": run.id, "rich_id": rich.id, "thin_id": thin.id, "empty_id": empty.id}


@pytest.fixture()
def seeded_run_with_theme(seeded_run):
    from phoenix.db import get_session

    with get_session() as session:
        tv = ThemeVersion(phoenix_run_id=seeded_run["run_id"], version_number=1, is_active=True)
        session.add(tv)
        session.flush()

        theme = OpportunityTheme(theme_version_id=tv.id, theme_name="Scheduling & Coordination")
        session.add(theme)
        session.flush()

        session.add(ThemeClusterAssignment(theme_id=theme.id, cluster_id=seeded_run["rich_id"]))

        seeded_run["theme_version_id"] = tv.id
        seeded_run["theme_id"] = theme.id
    return seeded_run


# --------------------------------------------------------------------
# 2026-08-02 additions — see module docstring above
# --------------------------------------------------------------------

class FakeModelServiceM4:
    """
    Canned response matching phoenix/solution_generation/generator.py's
    real prompt/response contract. All field values below are checked
    against the real patterns.py registries and validate.py's
    REQUIRED_FIELDS / duplicate rules, and confirmed passing via a real
    (not simulated) run of validate_candidates().
    """

    _VARIANTS = [
        {
            "solution_type": "Micro SaaS",
            "commercial_patterns": ["Subscription"],
            "revenue_model": "Subscription",
            "value_proposition": "Automated status updates close the loop for recruiters",
        },
        {
            "solution_type": "Browser Extension",
            "commercial_patterns": ["One-Time Purchase"],
            "revenue_model": "One-Time Purchase",
            "value_proposition": "One-click candidate status checks inside the ATS itself",
        },
        {
            "solution_type": "API",
            "commercial_patterns": ["Usage Based"],
            "revenue_model": "Usage Based",
            "value_proposition": "A drop-in webhook that notifies candidates automatically",
        },
    ]

    def __init__(self):
        self.calls = []
        self.next_response = None

    def _candidate(self, n: int, variant: dict) -> dict:
        return {
            "working_title": f"Test Solution {n}",
            "solution_type": variant["solution_type"],
            "estimated_customer_type": "Business",
            "target_customer": "Independent recruiters",
            "customer_problem": "Candidates are ghosted after the first call",
            "value_proposition": variant["value_proposition"],
            "commercial_patterns": variant["commercial_patterns"],
            "revenue_model": variant["revenue_model"],
            "delivery_model": "Web app",
            "pricing_strategy": "Tiered monthly",
            "automation_potential": "High — status updates can be fully automated",
            "estimated_build_complexity": "Low",
            "estimated_time_to_mvp": "4-6 weeks",
            "required_skills": ["Python", "Automation"],
            "primary_risks": ["Low switching cost for competitors"],
            "key_assumptions": ["Recruiters will pay for automated updates"],
            "confidence": "Medium",
            "reasoning": {
                "why_fits": "test fixture reasoning",
                "evidence_support": "test fixture reasoning",
                "unverified_assumptions": "test fixture reasoning",
                "why_alternative": "test fixture reasoning",
            },
        }

    def complete(self, prompt: str, model: str | None = None, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "model": model, "kwargs": kwargs})
        if self.next_response is not None:
            resp = self.next_response
            self.next_response = None
            return resp

        return json.dumps(
            [self._candidate(i + 1, variant) for i, variant in enumerate(self._VARIANTS)]
        )


@pytest.fixture()
def fake_model_service_m4(monkeypatch):
    """Patches get_model_service/get_logging_service as imported into
    phoenix.solution_generation.report."""
    import phoenix.solution_generation.report as solgen_report_module

    svc = FakeModelServiceM4()
    monkeypatch.setattr(solgen_report_module, "get_model_service", lambda: svc)
    monkeypatch.setattr(solgen_report_module, "get_logging_service", lambda: NullLoggingService())
    return svc


@pytest.fixture()
def seeded_scoring_version(db):
    """
    Seeds one ScoringVersion row. Columns confirmed 2026-08-02 against
    Carl's real error output (a real IntegrityError from an earlier
    version of this fixture that only set phoenix_run_id/scoring_version):
    module_version, prompt_version, model_used, and hash are all NOT
    NULL with no default; temperature defaults to 0.0, evidence_count
    defaults to 0, is_active defaults to True, theme_version_id is a
    nullable FK. Real phoenix/scoring/models.py itself still wasn't
    provided directly this session, but its actual constraints are now
    confirmed from that failure, not guessed.
    """
    from phoenix.db import get_session
    from phoenix.scoring.models import ScoringVersion

    with get_session() as session:
        run = PhoenixRun(topic="recruitment")
        session.add(run)
        session.flush()

        sv = ScoringVersion(
            phoenix_run_id=run.id,
            scoring_version=1,
            module_version="test-fixture",
            prompt_version="test-fixture",
            model_used="test-fixture",
            temperature=0.0,
            hash="test-fixture-hash",
        )
        session.add(sv)
        session.flush()

        return {"run_id": run.id, "scoring_version": sv.scoring_version, "scoring_version_id": sv.id}


class FakeModelServiceM5:
    """
    Canned response matching phoenix/commercial_validation/validator.py's
    real prompt/response contract. Field names (overall_recommendation,
    validation_confidence, the 9 SCORE_FIELDS) confirmed directly
    against the real commercial_validation/models.py and categories.py.
    """

    def __init__(self):
        self.calls = []
        self.next_response = None

    def complete(self, prompt: str, model: str | None = None, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "model": model, "kwargs": kwargs})
        if self.next_response is not None:
            resp = self.next_response
            self.next_response = None
            return resp

        from phoenix.commercial_validation.validator import SCORE_FIELDS

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


@pytest.fixture()
def fake_model_service_m5(monkeypatch):
    """Patches get_model_service/get_logging_service as imported into
    phoenix.commercial_validation.report."""
    import phoenix.commercial_validation.report as cv_report_module

    svc = FakeModelServiceM5()
    monkeypatch.setattr(cv_report_module, "get_model_service", lambda: svc)
    monkeypatch.setattr(cv_report_module, "get_logging_service", lambda: NullLoggingService())
    return svc


@pytest.fixture()
def mock_opportunity_entry(monkeypatch, seeded_scoring_version):
    """
    Monkeypatches get_opportunity_entry as imported into
    phoenix.solution_generation.report, returning a fixed entry dict
    for any (run_id, cluster_id) — matches fetch_entry.py's real,
    confirmed return shape: {"entry", "audit", "run_id", "scoring_version"}.
    Shared by test_solution_generation.py and test_commercial_validation.py
    (Module 5's tests need Module 4 blueprints to exist first).

    "audit" content here is a plausible placeholder — phoenix/scoring/
    report.py's real audit-block shape wasn't available this session.
    """
    import phoenix.solution_generation.report as solgen_report_module

    entry = {
        "run_id": seeded_scoring_version["run_id"],
        "scoring_version": seeded_scoring_version["scoring_version"],
        "audit": {
            "module_version": "test-fixture",
            "prompt_version": "test-fixture",
            "model_used": "test-fixture",
            "temperature": 0.0,
            "hash": "test-fixture-hash",
        },
        "entry": {
            "opportunity_id": 16,
            "status": "Scored",
            "problem_statement": "Recruiters ghost candidates after the first call",
            "scoring_explanation": {
                "why": "High frequency, high severity, low competition saturation",
                "evidence_used": [
                    {"source_type": "reddit", "source_url": "https://reddit.com/r/recruiting/1"},
                ],
            },
            "overall_score": 72.5,
            "commercial_confidence": "Medium",
        },
    }
    monkeypatch.setattr(
        solgen_report_module, "get_opportunity_entry", lambda run_id, cluster_id, scoring_version=None: entry
    )
    return entry
