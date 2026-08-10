"""
Agent Reach Collector Contract

Every collector must inherit from BaseCollector and implement collect().

Collectors NEVER write directly to Phoenix.

Collectors NEVER perform deduplication.

Collectors NEVER normalise evidence.

Their only responsibility is to retrieve raw evidence from one source.

The runner, normalizer and Phoenix integration handle everything else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseCollector(ABC):
    """Abstract base class for every Agent Reach collector."""

    #: Human readable collector name
    name: str = "Unnamed Collector"

    #: Collector version
    version: str = "1.0"

    #: Whether this collector is enabled
    enabled: bool = True

    @abstractmethod
    def collect(self) -> list[dict[str, Any]]:
        """
        Return raw evidence.

        The returned dictionaries are intentionally source-specific.

        Example:

        [
            {
                "title": "...",
                "body": "...",
                "url": "...",
                "author": "...",
                "created": "...",
            }
        ]
        """
        raise NotImplementedError