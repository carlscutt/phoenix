from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phoenix.models import Base, TimestampMixin


class BusinessBlueprintVersion(Base, TimestampMixin):
    """
    One row per Business Blueprint generation run for a given
    solution_public_id. Only one version may be active per solution at a
    time (spec §7). Per Decision 4, this is the document itself — there is
    no separate BusinessBlueprint model. Per Decision 2, this table carries
    no ForeignKey to any other module's tables.

    CORRECTED 2026-08-03 (third pass on this file — see the two earlier
    corrections' history if you want it, not repeated here): added
    blueprint_version. Every other module's version table
    (SolutionGenerationVersion.generation_version, ValidationVersion.
    validation_version, ScoringVersion.scoring_version) has an explicit,
    per-entity incrementing integer alongside is_active — this file
    didn't, which report.py (Step 8) needs to actually implement
    versioning the same way every other module does (next_version_number
    = count of existing versions for this solution_public_id, plus 1).
    Safe to add now — no BusinessBlueprintVersion rows have ever been
    persisted yet (Step 8, which would be the first thing to write one,
    didn't exist until now), so this isn't a migration, just a pre-first-
    use fix.

    correlation_id: confirmed against the real solution_generation/report.py
    and commercial_validation/report.py — NEITHER module persists a
    correlation_id column on its own version table at all; both only use
    correlation_id=str(cluster_id) as a per-log-call parameter to
    LoggingService. Kept as a nullable column here (harmless, and useful
    for the Studio UI to display), populated with str(cluster_id) by
    report.py — same value, not a separately "inherited" one, since spec
    §14's premise (something real to inherit from Module 5) turned out
    not to exist.
    """

    __tablename__ = "phoenix_business_blueprint_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Explicit selection key per Decision 3.
    solution_public_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Per-solution incrementing version number, same pattern as
    # generation_version / validation_version / scoring_version in
    # every other module.
    blueprint_version: Mapped[int] = mapped_column(Integer, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Audit fields — same shape as scoring/audit.py, solution_generation/audit.py,
    # commercial_validation/audit.py.
    module_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    audit_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    sections: Mapped[List["BusinessBlueprintSection"]] = relationship(
        "BusinessBlueprintSection",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="BusinessBlueprintSection.sort_order",
    )


class BusinessBlueprintSection(Base, TimestampMixin):
    """
    One row per generated section (spec §6's 17 leaf sections, grouped into
    the six bounded generation groups from categories.py's BATCH_GROUPS).
    """

    __tablename__ = "phoenix_business_blueprint_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("phoenix_business_blueprint_versions.id"),
        nullable=False,
        index=True,
    )

    section_group: Mapped[str] = mapped_column(String(32), nullable=False)
    section_name: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)

    version: Mapped["BusinessBlueprintVersion"] = relationship(
        "BusinessBlueprintVersion", back_populates="sections"
    )


# Re-triggers table creation now that these classes exist on Base.metadata
# — same pattern every other module's real models.py uses.
from phoenix.db import init_db as _init_db  # noqa: E402

_init_db()
