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
