"""
Agent Reach Normalizer

Converts raw collector output into canonical Evidence objects.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import Evidence


def normalize(source: str, item: dict[str, Any]) -> Evidence:
    """
    Convert one raw collector record into a canonical Evidence object.

    Missing fields are safely defaulted.
    """

    return Evidence(
        source=source,
        external_id=item.get("external_id"),
        title=item.get("title", ""),
        content=item.get("content", ""),
        url=item.get("url", ""),
        author=item.get("author"),
        published_at=item.get("published_at"),
        collected_at=datetime.utcnow(),
        language=item.get("language"),
        tags=item.get("tags", []),
        metadata=item.get("metadata", {}),
    )