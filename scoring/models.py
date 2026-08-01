"""
Module 3 tables. Lives in the same phoenix.db as Modules 1 and 2 — same
"each subsystem owns its own local DB" precedent, same TimestampMixin,
same Mapped/mapped_column style as the rest of phoenix/models.py.

Corrected 2026-07-28 against Carl's real schema (previously guessed at
table/column names without file access — see PHOENIX_MODULE3_HANDOFF.md
§1 for what changed and why):
  - FKs point at the real prefixed table names (phoenix_runs,
    phoenix_complaint_clusters, phoenix_theme_versions).
  - Uses TimestampMixin instead of a hand-rolled created_at column,
    matching PhoenixRun/ComplaintCluster/ThemeVersion/etc.
  - Mapped[]/mapped_column() typed style instead of old-style Column(),
    matching the rest of the file.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import String, Float, Boolean, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phoenix.models import Base, TimestampMixin


class ScoringVersion(TimestampMixin, Base):
    """
    One scoring run against a PhoenixRun's clusters. Mirrors the
    ThemeVersion pattern: never overwritten, one active version per
    run, prior versions retained for audit/history.
    """

    __tablename__ = "phoenix_scoring_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phoenix_run_id: Mapped[int] = mapped_column(ForeignKey("phoenix_runs.id"), nullable=False)
    scoring_version: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3... per run
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Theme enrichment, per §5 of the architecture spec — nullable since
    # Module 2 is optional (Decision 2).
    theme_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("phoenix_theme_versions.id"), nullable=True
    )

    module_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex digest

    entries: Mapped[list["OpportunityScoreEntry"]] = relationship(
        back_populates="scoring_version", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ScoringVersion id={self.id} run={self.phoenix_run_id} "
            f"v{self.scoring_version} active={self.is_active}>"
        )


class OpportunityScoreEntry(TimestampMixin, Base):
    """One scored cluster within a ScoringVersion."""

    __tablename__ = "phoenix_opportunity_score_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scoring_version_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_scoring_versions.id"), nullable=False
    )

    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_complaint_clusters.id"), nullable=False
    )
    theme_id: Mapped[int | None] = mapped_column(
        ForeignKey("phoenix_opportunity_themes.id"), nullable=True
    )

    # Added for Module 4 (Solution Generation Engine), 2026-07-30 — approved
    # non-breaking extension, see MODULE_04_SPECIFICATION.md §22a / decision 3.
    # Sourced from ComplaintCluster.representative_text at score_run() time;
    # previously that text was read into report.py's internal ai_inputs dict
    # for prompt use only and never persisted or returned. Every existing
    # caller of score_run()/get_score_report() is unaffected — this is a
    # pure addition, nothing renamed or removed.
    problem_statement: Mapped[str] = mapped_column(String, nullable=False, default="")

    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # "Scored" | "Insufficient Evidence"
    commercial_confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    recommended_priority: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ranking_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    weights_applied: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    scoring_explanation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    supporting_evidence_refs: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)

    scoring_version: Mapped["ScoringVersion"] = relationship(back_populates="entries")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<OpportunityScoreEntry id={self.id} cluster={self.cluster_id} "
            f"score={self.overall_score} status={self.status}>"
        )


# phoenix/db.py runs init_db() at import time — but that happens the
# moment `phoenix.db` is first imported, which in report.py is BEFORE
# this module (and therefore ScoringVersion/OpportunityScoreEntry) has
# been imported. Base.metadata only knows about classes that have
# already been defined, so the first init_db() call creates every
# Module 1/2 table but not these two. db.py's own docstring documents
# init_db() as "safe to call repeatedly — create_all only creates
# what's missing", so re-running it here (now that these classes exist
# on Base.metadata) is the correct fix — not an import-order fragility
# to work around in report.py, which could break again depending on
# what else happens to import phoenix.db first in a given entry point
# (CLI script vs. Dashboard vs. a bare python3 -c one-liner).
from phoenix.db import init_db as _init_db  # noqa: E402

_init_db()
