"""
Data model for Phoenix — Opportunity Intelligence System, Module 1
(Opportunity Discovery). Per PHOENIX_ARCHITECTURE.md and the approved
architecture decisions.

Same SQLAlchemy pattern as the rest of the platform: a TimestampMixin
every table gets, one SQLite DB for this subsystem (phoenix.db), JSON
columns for naturally-nested structures. Phoenix owns its own DB —
same "each subsystem owns its own local DB" precedent as builder.db,
atlas.db, observer.db, workflow_engine.db.

Decisions this schema encodes (see PHOENIX_ARCHITECTURE.md §6 /
approved decisions doc):
  - Run tracking is Phoenix's own PhoenixRun — NOT WorkflowRun. There
    is no Gate 1 / Gate 2 concept here; Opportunity Discovery never
    writes files, so there's nothing to govern.
  - Complaint clustering (this module) is mechanical near-duplicate
    merging only — ComplaintCluster.occurrence_count, no semantic
    "theme" field baked into the cluster row itself. Thematic grouping
    (Module 2, see below) is layered on top via a separate join, never
    by adding a theme column directly to ComplaintCluster.
  - OpportunityReport carries a confidence score that must be
    evidence-based and explainable — confidence_score plus the raw
    counts it was derived from, plus a required explanation string,
    so "why this score" is always answerable from the row itself.
  - Evidence always retains its source_url — non-negotiable per the
    architecture doc ("the whole system's credibility rests on
    evidence-based").

Module 2 (Thematic Grouping) additions — PHOENIX_MODULE2_ARCHITECTURE.md,
approved decisions 2026-07-25:
  - Theme reports are versioned, never overwritten (approved decision).
    A ComplaintCluster's theme assignment differs by version, so it
    can't be a single FK column on ComplaintCluster the way
    Complaint.cluster_id works for Module 1 — that only holds one
    value. Instead: ThemeVersion (one row per theming attempt on a
    run, exactly one is_active=True per run) owns OpportunityTheme
    rows, and ThemeClusterAssignment joins a specific version's themes
    to clusters. Old versions stay fully queryable for audit/
    comparison; nothing is deleted on re-theming, a new ThemeVersion
    is added and the previous one's is_active flips to False.
  - "Other" bucket is not a special case in the schema — it is an
    ordinary OpportunityTheme row (theme_name="Other"). The ~10% cap
    and "recommend a new theme instead" logic are theming.py's
    responsibility at generation time, not something the schema
    enforces.
"""
from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )


class PhoenixRun(TimestampMixin, Base):
    """One Opportunity Discovery run for a topic. Deliberately minimal —
    this is a research workflow, not a governed code-generation one, so
    it does not reuse WorkflowRun's Gate 1/Gate 2-shaped status model.
    """

    __tablename__ = "phoenix_runs"

    STATUSES = ("pending", "running", "completed", "failed")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    sources_used: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    complaints: Mapped[list["Complaint"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    clusters: Mapped[list["ComplaintCluster"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    report: Mapped["OpportunityReport | None"] = relationship(
        back_populates="run", cascade="all, delete-orphan", uselist=False
    )
    theme_versions: Mapped[list["ThemeVersion"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return f"<PhoenixRun id={self.id} topic={self.topic!r} status={self.status}>"


class Evidence(TimestampMixin, Base):
    """One raw piece of public content fetched by a collector. source_url
    is always retained — the report's credibility depends on every
    complaint being traceable back to a real, checkable source.
    """

    __tablename__ = "phoenix_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phoenix_run_id: Mapped[int] = mapped_column(ForeignKey("phoenix_runs.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "reddit"
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    run: Mapped["PhoenixRun"] = relationship(back_populates="evidence")
    complaints: Mapped[list["Complaint"]] = relationship(back_populates="evidence")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Evidence id={self.id} source={self.source_type} run={self.phoenix_run_id}>"


class Complaint(TimestampMixin, Base):
    """One extracted complaint statement. Structured output only —
    {complaint_text, source_url, source_type, raw_snippet} shape per
    the architecture doc, never a free-form summary.
    """

    __tablename__ = "phoenix_complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phoenix_run_id: Mapped[int] = mapped_column(ForeignKey("phoenix_runs.id"), nullable=False)
    evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("phoenix_evidence.id"), nullable=True
    )
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("phoenix_complaint_clusters.id"), nullable=True
    )
    complaint_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)

    run: Mapped["PhoenixRun"] = relationship(back_populates="complaints")
    evidence: Mapped["Evidence | None"] = relationship(back_populates="complaints")
    cluster: Mapped["ComplaintCluster | None"] = relationship(back_populates="complaints")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Complaint id={self.id} cluster={self.cluster_id}>"


class ComplaintCluster(TimestampMixin, Base):
    """A group of near-identical complaints, mechanically merged
    (text-similarity based — Module 1 does NOT do semantic/thematic
    grouping; that's Module 2). occurrence_count is the whole point of
    Module 1's clustering: how many times did this same complaint show
    up, across how many distinct sources.
    """

    __tablename__ = "phoenix_complaint_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phoenix_run_id: Mapped[int] = mapped_column(ForeignKey("phoenix_runs.id"), nullable=False)
    representative_text: Mapped[str] = mapped_column(Text, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_diversity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    run: Mapped["PhoenixRun"] = relationship(back_populates="clusters")
    complaints: Mapped[list["Complaint"]] = relationship(back_populates="cluster")
    theme_assignments: Mapped[list["ThemeClusterAssignment"]] = relationship(
        back_populates="cluster"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ComplaintCluster id={self.id} occurrences={self.occurrence_count} "
            f"diversity={self.source_diversity}>"
        )


class OpportunityReport(TimestampMixin, Base):
    """The final assembled report for one PhoenixRun. confidence_score
    must always be explainable — confidence_explanation is required
    (not nullable) so a score is never presented without the reasoning
    behind it, per the approved decision that Phoenix produces
    evidence-based intelligence, not subjective recommendations.
    """

    __tablename__ = "phoenix_opportunity_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phoenix_run_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_runs.id"), unique=True, nullable=False
    )
    topic: Mapped[str] = mapped_column(String(200), nullable=False)

    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False)

    complaints_analysed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_clusters_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_analysed: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    time_period_start: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    time_period_end: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["PhoenixRun"] = relationship(back_populates="report")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<OpportunityReport id={self.id} topic={self.topic!r} "
            f"confidence={self.confidence_score}>"
        )


class ThemeVersion(TimestampMixin, Base):
    """One theming attempt on a PhoenixRun's clusters. Versioned per the
    approved Module 2 decision — theme reports are never overwritten.
    Re-running theming adds a new ThemeVersion and flips the previous
    one's is_active to False; it does not delete or mutate it. Exactly
    one ThemeVersion per run should have is_active=True at a time —
    enforced at the application layer (phoenix_actions.py), not by a
    DB constraint, matching how PhoenixRun.status is also
    application-managed rather than DB-enforced.
    """

    __tablename__ = "phoenix_theme_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phoenix_run_id: Mapped[int] = mapped_column(ForeignKey("phoenix_runs.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    other_bucket_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    run: Mapped["PhoenixRun"] = relationship(back_populates="theme_versions")
    themes: Mapped[list["OpportunityTheme"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ThemeVersion id={self.id} run={self.phoenix_run_id} "
            f"v{self.version_number} active={self.is_active}>"
        )


class OpportunityTheme(TimestampMixin, Base):
    """One business-theme grouping within a ThemeVersion, e.g.
    "Recruitment Administration" covering CV-rewriting and
    cover-letter complaints. Scoped to a version, not to the run
    directly — the same theme name can recur (or change) across
    versions, and each version's set of themes is independent.

    The "Other" bucket (per the approved ~10% cap decision) is not a
    special case here — it's an ordinary row with theme_name="Other".
    The cap and the "recommend a new theme instead" behavior when it's
    exceeded are theming.py's responsibility at generation time.
    """

    __tablename__ = "phoenix_opportunity_themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    theme_version_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_theme_versions.id"), nullable=False
    )
    theme_name: Mapped[str] = mapped_column(String(200), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    version: Mapped["ThemeVersion"] = relationship(back_populates="themes")
    cluster_assignments: Mapped[list["ThemeClusterAssignment"]] = relationship(
        back_populates="theme", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OpportunityTheme id={self.id} name={self.theme_name!r}>"


class ThemeClusterAssignment(TimestampMixin, Base):
    """Join row: which ComplaintCluster belongs to which OpportunityTheme,
    for one specific ThemeVersion. A join table rather than a FK column
    on ComplaintCluster because a cluster's theme assignment differs
    per version — a single FK column could only ever hold one version's
    answer, which is exactly what versioning must not do.
    """

    __tablename__ = "phoenix_theme_cluster_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    theme_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_opportunity_themes.id"), nullable=False
    )
    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("phoenix_complaint_clusters.id"), nullable=False
    )

    theme: Mapped["OpportunityTheme"] = relationship(back_populates="cluster_assignments")
    cluster: Mapped["ComplaintCluster"] = relationship(back_populates="theme_assignments")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ThemeClusterAssignment theme={self.theme_id} cluster={self.cluster_id}>"
