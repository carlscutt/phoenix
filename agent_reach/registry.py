"""
Collector Registry

Keeps track of every available Agent Reach collector.

The runner executes collectors from this registry rather than importing
individual collectors directly.
"""

from __future__ import annotations

from typing import Iterable

from .base import BaseCollector


class CollectorRegistry:
    """Registry of available collectors."""

    def __init__(self) -> None:
        self._collectors: list[BaseCollector] = []

    def register(self, collector: BaseCollector) -> None:
        """Register a collector."""
        self._collectors.append(collector)

    def enabled(self) -> Iterable[BaseCollector]:
        """Return enabled collectors."""
        return (c for c in self._collectors if c.enabled)

    def all(self) -> list[BaseCollector]:
        """Return every registered collector."""
        return list(self._collectors)

    def names(self) -> list[str]:
        """Return collector names."""
        return [c.name for c in self._collectors]


registry = CollectorRegistry()