"""
Agent Reach Audit

Records the outcome of every collector execution.

Designed to integrate naturally with Phoenix's existing
versioning and audit philosophy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


@dataclass(slots=True)
class AuditRecord:

    run_id: str = field(default_factory=lambda: str(uuid4()))

    collector: str = ""

    collector_version: str = ""

    started: datetime = field(default_factory=datetime.utcnow)

    finished: datetime | None = None

    items_collected: int = 0

    duplicates_removed: int = 0

    errors: list[str] = field(default_factory=list)

    success: bool = True