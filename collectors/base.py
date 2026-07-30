"""
Common collector interface for Phoenix evidence sources.

Per PHOENIX_ARCHITECTURE.md §3 step 3: "Every collector implements one
common interface (`fetch(query) -> list[Evidence]`) so adding a new
source later never touches existing ones."

Collectors return plain `RawEvidence` dataclasses, NOT the
`phoenix.models.Evidence` ORM rows directly — collectors have no DB
session and shouldn't need one. Whatever calls a collector (the
not-yet-built orchestration layer) is responsible for turning
`RawEvidence` into persisted `Evidence` rows against a specific
`PhoenixRun`. This keeps collectors trivially unit-testable (no DB
required) and keeps "one subsystem owns its own DB" clean — a
collector never writes to phoenix.db itself.

source_url is required and must always be a real, checkable link —
non-negotiable per the architecture doc: the whole system's
credibility rests on every complaint being traceable to real evidence.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawEvidence:
    """One piece of raw public content fetched by a collector, before
    it's persisted as a `phoenix.models.Evidence` row."""

    source_type: str
    source_url: str
    raw_snippet: str
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_url:
            raise ValueError("RawEvidence.source_url is required and cannot be empty")
        if not self.raw_snippet or not self.raw_snippet.strip():
            raise ValueError("RawEvidence.raw_snippet is required and cannot be empty")


class BaseCollector(ABC):
    """Every source-specific collector subclasses this. `source_type`
    must match the string used elsewhere in Phoenix (PhoenixRun.
    sources_used, Evidence.source_type, Complaint.source_type) so
    reports can group/filter by source consistently.
    """

    source_type: str

    @abstractmethod
    def fetch(self, query: str, max_results: int = 50) -> list[RawEvidence]:
        """Fetch up to `max_results` pieces of public evidence relevant
        to `query`. Must not raise on "no results" (return `[]`
        instead) — only raise for genuine failures (auth, network,
        malformed response) that the caller needs to know about.
        """
        raise NotImplementedError
