from __future__ import annotations

import json

from phoenix.collectors.base import BaseCollector
from phoenix.integrations.agent_reach.evidence import collect


class GitHubCollector(BaseCollector):
    name = "GitHub"
    version = "2.0"
    enabled = True

    def fetch(
        self,
        query: str,
        limit: int = 25,
    ) -> list[dict]:
        """
        Collect public GitHub evidence using the backend
        currently provisioned by Agent Reach.

        Parameters are supplied by Phoenix.
        No acquisition logic is duplicated here.
        """

        result = collect(
            [
                "gh",
                "search",
                "issues",
                query,
                "--limit",
                str(limit),
                "--json",
                "number,title,body,url,author,createdAt,state,repository",
            ]
        )

        issues = json.loads(result.stdout)

        evidence: list[dict] = []

        for issue in issues:
            evidence.append(
                {
                    "external_id": str(issue["number"]),
                    "title": issue["title"],
                    "content": issue.get("body") or "",
                    "url": issue["url"],
                    "author": issue["author"]["login"],
                    "published_at": issue["createdAt"],
                    "metadata": {
                        "state": issue["state"],
                        "repository": issue["repository"]["nameWithOwner"],
                    },
                }
            )

        return evidence