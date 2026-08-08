"""
Agent Reach Runner

Executes every enabled collector and returns all collected evidence.

The runner knows nothing about individual collectors.
"""

from __future__ import annotations

from typing import Any

from .registry import registry


class AgentReachRunner:
    """Runs all enabled collectors."""

    def run(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for collector in registry.enabled():
            print(f"[Agent Reach] Running {collector.name}")

            try:
                evidence = collector.collect()

                if evidence:
                    results.extend(evidence)

            except Exception as exc:
                print(f"[Agent Reach] {collector.name} failed: {exc}")

        return results


runner = AgentReachRunner()