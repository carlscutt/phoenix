"""
Agent Reach Repository

Persists normalized Evidence objects into Phoenix.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select

from db import get_session
from models import Evidence as PhoenixEvidence

from agent_reach.models import Evidence


class EvidenceRepository:
    """Persists Agent Reach evidence into Phoenix."""

    def save_many(
        self,
        run_id: int,
        evidence_items: Iterable[Evidence],
    ) -> dict[str, int]:
        """
        Persist a batch of Evidence objects.

        Returns
        -------
        {
            "inserted": int,
            "duplicates": int,
        }
        """

        inserted = 0
        duplicates = 0

        evidence_items = list(evidence_items)

        with get_session() as session:

            # Collect all external IDs from this batch
            incoming_ids = {
                e.external_id
                for e in evidence_items
                if e.external_id
            }

            # Fetch existing IDs with a single query
            existing_ids: set[str] = set()

            if incoming_ids:
                rows = session.execute(
                    select(PhoenixEvidence.external_id).where(
                        PhoenixEvidence.external_id.in_(incoming_ids)
                    )
                ).scalars()

                existing_ids = set(rows)

            for evidence in evidence_items:

                if (
                    evidence.external_id
                    and evidence.external_id in existing_ids
                ):
                    duplicates += 1
                    continue

                session.add(
                    PhoenixEvidence(
                        phoenix_run_id=run_id,
                        source_type=evidence.source,
                        source_url=evidence.url,
                        raw_snippet=evidence.content,
                        fetched_at=evidence.collected_at,
                        external_id=evidence.external_id,
                        extra=evidence.metadata,
                    )
                )

                if evidence.external_id:
                    existing_ids.add(evidence.external_id)

                inserted += 1

        return {
            "inserted": inserted,
            "duplicates": duplicates,
        }


repository = EvidenceRepository()