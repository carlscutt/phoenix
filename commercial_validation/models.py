"""
Module 5 tables. Lives in the same phoenix.db as Modules 1-4 — same
"each subsystem owns its own local DB" precedent (in practice: one
shared phoenix.db, phoenix_-prefixed tables per module), same
TimestampMixin, same Mapped/mapped_column style as
phoenix/scoring/models.py and phoenix/solution_generation/models.py.

Scoping decision (approved in the Module 5 Build Order): ValidationVersion
is scoped to solution_generation_version_id, not to an individual
blueprint — one validation run covers every active blueprint under a
given SolutionGenerationVersion, so the comparative pass (spec §9) has a
complete, same-opportunity set to compare within one version.
ValidatedSolutionBlueprint rows store solution_public_id (Module 4's
public_id string, e.g. SBP-xxxxxxxx) rather than a cross-subsystem
foreign key — same isolation approach Module 4 itself uses toward
Module 3.

Score-range / weighting assumption, flagged rather than silently baked
in as final: MODULE_05_SPECIFICATION.md §6/§8 names nine score
categories but gives no explicit numeric range or weighting scheme
(unlike Module 3, which specified exact percentage weights per
category). This implementation uses 0-100 per category and an
unweighted mean for overall_validation_score (see
commercial_validation/report.py::_overall_score) as the most defensible
default until real weights are supplied — confirm/adjust before this
gets relied on for real ranking decisions.

Same init_db()-ordering requirement as every prior module's models.py:
db.py's init_db() fires the moment phoenix.db is first imported, before
this module's classes exist on Base.metadata if something else imports
phoenix.db first. Re-running it at the bottom of this file (safe —
create_all() only creates what's missing) is the same fix used in
scoring/models.py and solution_generation/models.py.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import String, Float, Boolean, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phoenix.models import Base, TimestampMixin

# ValidationVersion's ForeignKey below targets
# phoenix_solution_generation_versions, which only exists on
# Base.metadata once phoenix.solution_generation.models has actually
# been imported somewhere in the process — and that module's own FKs
# (to phoenix_scoring_versions) have the same requirement one level
# further out. In the live Flask app this happens to already be
# satisfied by the time these get imported, because something earlier
# in phoenix_actions.py's own import chain loads scoring first. This
# module doesn't rely on that ambient ordering — it imports both
# explicitly, in dependency order, purely for the Table-registration
# side effect, so commercial_validation/models.py works correctly
# regardless of what else has or hasn't been imported yet.
import phoenix.scoring.models  # noqa: F401
import phoenix.solution_generation.models  # noqa: F401


class ValidationVersion(TimestampMixin, Base):
    """
    One validation run against every active blueprint under a single
    SolutionGenerationVersion. Mirrors the SolutionGenerationVersion /
    ScoringVersion pattern: never overwritten, one active version per
    solution_generation_version_id, prior versions retained for
    audit/history.
    """

    __tablename__ = "phoenix_validation_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solution_generation_version_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_solution_generation_versions.id"), nullable=False
    )
    validation_version: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3... per generation version
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    module_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex digest

    # Spec §9: comparative pass across every blueprint in this version —
    # which solution_public_id came out strongest, and the full ranking,
    # kept explainable. Deterministic (see report.py), computed in the
    # orchestrator, never inside the AI prompt (Comparative Validation
    # Rule). One JSON blob, same shape choice as SolutionBlueprint.reasoning.
    comparative_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    validated_blueprints: Mapped[list["ValidatedSolutionBlueprint"]] = relationship(
        back_populates="validation_version", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ValidationVersion id={self.id} "
            f"generation={self.solution_generation_version_id} "
            f"v{self.validation_version} active={self.is_active}>"
        )


class ValidatedSolutionBlueprint(TimestampMixin, Base):
    """One validated business concept within a ValidationVersion."""

    __tablename__ = "phoenix_validated_solution_blueprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_version_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_validation_versions.id"), nullable=False
    )

    # Module 4's public_id string — not a cross-subsystem FK, same
    # isolation approach Module 4 itself uses toward Module 3.
    solution_public_id: Mapped[str] = mapped_column(String(20), nullable=False)

    # Spec §8 category scores, 0-100 each (see module docstring assumption).
    market_need_score: Mapped[float] = mapped_column(Float, nullable=False)
    customer_pain_score: Mapped[float] = mapped_column(Float, nullable=False)
    revenue_potential_score: Mapped[float] = mapped_column(Float, nullable=False)
    competition_score: Mapped[float] = mapped_column(Float, nullable=False)
    technical_complexity_score: Mapped[float] = mapped_column(Float, nullable=False)
    time_to_mvp_score: Mapped[float] = mapped_column(Float, nullable=False)
    founder_fit_score: Mapped[float] = mapped_column(Float, nullable=False)
    ai_leverage_score: Mapped[float] = mapped_column(Float, nullable=False)
    defensibility_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Unweighted mean of the nine scores above — see module docstring
    # assumption; adjust in report.py::_overall_score if real weights
    # are supplied later. This column doesn't need to change either way.
    overall_validation_score: Mapped[float] = mapped_column(Float, nullable=False)

    overall_recommendation: Mapped[str] = mapped_column(String(30), nullable=False)
    validation_confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    validation_explanation: Mapped[str] = mapped_column(String, nullable=False)

    strengths: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    weaknesses: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    primary_risks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    suggested_improvements: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    validation_version: Mapped["ValidationVersion"] = relationship(
        back_populates="validated_blueprints"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ValidatedSolutionBlueprint solution={self.solution_public_id} "
            f"recommendation={self.overall_recommendation}>"
        )


# See module docstring: init_db() must run again here now that these two
# classes exist on Base.metadata, mirroring solution_generation/models.py.
from phoenix.db import init_db as _init_db  # noqa: E402

_init_db()
