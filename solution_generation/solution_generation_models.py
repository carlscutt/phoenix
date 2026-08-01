"""
Module 4 tables. Lives in the same phoenix.db as Modules 1-3 — same
"each subsystem owns its own local DB" precedent, same TimestampMixin,
same Mapped/mapped_column style as phoenix/scoring/models.py.

Per MODULE_04_SPECIFICATION.md v1.3:
  - §6a Versioning: SolutionGenerationVersion mirrors ScoringVersion —
    never overwritten, one active version per (scoring_version_id,
    cluster_id) pair, prior versions retained for audit/history.
  - §18a Storage: Module 4 owns these tables directly, not MemoryService.
  - Recommendation 6 (Carl, 2026-07-30): every SolutionBlueprint gets a
    short public UUID (SBP-xxxxxxxx) at creation, distinct from its
    internal integer PK — this is the identifier Module 5+ and the UI
    reference; the integer PK stays purely internal to the ORM.

Known import-order trap, repeated deliberately from phoenix/scoring/models.py:
phoenix/db.py's init_db() fires the moment phoenix.db is first imported,
which happens BEFORE this module (and therefore these classes) exists on
Base.metadata if something else imports phoenix.db first. db.py's own
docstring documents init_db() as safe to call repeatedly (create_all only
creates what's missing) — so re-running it at the bottom of this file,
now that SolutionGenerationVersion/SolutionBlueprint exist on
Base.metadata, is the correct fix. This is not a one-off workaround for
this module; it will recur for any new module's models.py under the
current phoenix/db.py design.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String, Float, Boolean, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phoenix.models import Base, TimestampMixin


def _generate_public_id() -> str:
    """SBP-xxxxxxxx — short, human-referenceable, distinct from the DB PK."""
    return f"SBP-{uuid.uuid4().hex[:8]}"


class SolutionGenerationVersion(TimestampMixin, Base):
    """
    One solution-generation run against a single OpportunityScoreEntry.
    Mirrors the ScoringVersion pattern: never overwritten, one active
    version per (scoring_version_id, cluster_id) pair, prior versions
    retained for audit/history.

    Scoped to (scoring_version_id, cluster_id) rather than to a
    phoenix_run_id directly, because Module 4 operates on a single
    selected OpportunityScoreEntry (spec §5), and an entry is uniquely
    identified by which ScoringVersion it belongs to plus its cluster_id
    (cluster_id alone is not unique across re-scoring runs).
    """

    __tablename__ = "phoenix_solution_generation_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scoring_version_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_scoring_versions.id"), nullable=False
    )
    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_complaint_clusters.id"), nullable=False
    )
    generation_version: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3... per opportunity
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    module_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex digest

    blueprints: Mapped[list["SolutionBlueprint"]] = relationship(
        back_populates="generation_version", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SolutionGenerationVersion id={self.id} cluster={self.cluster_id} "
            f"v{self.generation_version} active={self.is_active}>"
        )


class SolutionBlueprint(TimestampMixin, Base):
    """One generated solution concept within a SolutionGenerationVersion."""

    __tablename__ = "phoenix_solution_blueprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, default=_generate_public_id
    )
    solution_generation_version_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_solution_generation_versions.id"), nullable=False
    )

    working_title: Mapped[str] = mapped_column(String(200), nullable=False)

    # Must be a member of patterns.SOLUTION_TYPES — enforced by Blueprint
    # Validation (spec §6b) before a row is ever persisted, not by a DB
    # constraint, since the registry is a Python-level list, not an enum
    # type in the schema (keeps it a one-file, no-migration change to
    # extend later, matching spec §8's "future categories must remain
    # additive").
    solution_type: Mapped[str] = mapped_column(String(50), nullable=False)

    estimated_customer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_customer: Mapped[str] = mapped_column(String(300), nullable=False)
    customer_problem: Mapped[str] = mapped_column(String, nullable=False)
    value_proposition: Mapped[str] = mapped_column(String, nullable=False)

    # One or more commercial patterns / a single revenue model, each
    # drawn from patterns.COMMERCIAL_PATTERNS / patterns.REVENUE_MODELS.
    commercial_patterns: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    revenue_model: Mapped[str] = mapped_column(String(50), nullable=False)

    delivery_model: Mapped[str] = mapped_column(String(200), nullable=False)
    pricing_strategy: Mapped[str] = mapped_column(String(300), nullable=False)
    automation_potential: Mapped[str] = mapped_column(String(200), nullable=False)
    estimated_build_complexity: Mapped[str] = mapped_column(String(50), nullable=False)
    estimated_time_to_mvp: Mapped[str] = mapped_column(String(50), nullable=False)

    required_skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    primary_risks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    key_assumptions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    confidence: Mapped[str] = mapped_column(String(10), nullable=False)  # Low | Medium | High

    # Added for the Approve Solution UI action (spec §17), 2026-07-31.
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Explainability (spec §11): why this solution fits, what evidence
    # supports it, what assumptions remain unverified, why alternatives
    # were also generated. Kept as one JSON blob, same shape choice as
    # OpportunityScoreEntry.scoring_explanation in phoenix/scoring/models.py.
    reasoning: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    generation_version: Mapped["SolutionGenerationVersion"] = relationship(
        back_populates="blueprints"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SolutionBlueprint {self.public_id} type={self.solution_type} "
            f"confidence={self.confidence}>"
        )


# See module docstring: init_db() must run again here now that these two
# classes exist on Base.metadata, mirroring phoenix/scoring/models.py.
from phoenix.db import init_db as _init_db  # noqa: E402

_init_db()
