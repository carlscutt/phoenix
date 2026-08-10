"""
Agent Reach Evidence Model

All collectors eventually produce Evidence objects after normalization.

Phoenix only ever consumes Evidence objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Evidence:
    """
    Canonical evidence representation.

    Every source is normalised into this object before
    entering Phoenix.
    """

    source: str
    title: str
    content: str
    url: str
    external_id: str | None = None

    author: str | None = None

    published_at: datetime | None = None

    collected_at: datetime = field(default_factory=datetime.utcnow)

    language: str | None = None

    tags: list[str] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)