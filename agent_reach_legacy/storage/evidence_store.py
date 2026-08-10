"""
Evidence Store

Persists normalized Agent Reach evidence into Phoenix.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from db import get_session
from agent_reach.models import Evidence


class EvidenceStore:
    """Persistence layer for Agent Reach evidence."""

    def save(self, evidence: Evidence) -> None:
        """
        Persist one normalized evidence object.

        Implementation added in the next step.
        """
        raise NotImplementedError


store = EvidenceStore()