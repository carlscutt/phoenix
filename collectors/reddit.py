from __future__ import annotations

import yaml

from collectors.base import BaseCollector
from integrations.agent_reach.adapter import doctor
from integrations.agent_reach.evidence import collect
from integrations.agent_reach.exceptions import BackendUnavailableError


class RedditCollector(BaseCollector):
    name = "Reddit"
    version = "2.0"
    enabled = True

    def fetch(
        self,
        query: str,
        limit: int = 25,
    ) -> list[dict]:
        """
        Collect Reddit evidence using the backend currently
        provisioned by Agent Reach.

        Phoenix supplies the search parameters.
        """

        status = doctor()

        backend = status["reddit"]["active_backend"]

        if backend is None:
            raise BackendUnavailableError(
                "No Reddit backend is currently provisioned by Agent Reach."
            )

        if backend == "OpenCLI":
            command = [
                "opencli",
                "reddit",
                "search",
                query,
                "-f",
                "yaml",
            ]

        elif backend == "rdt-cli":
            command = [
                "rdt",
                "search",
                query,
                "--limit",
                str(limit),
                "--yaml",
            ]

        else:
            raise BackendUnavailableError(
                f"Unsupported Reddit backend: {backend}"
            )

        result = collect(command)

        posts = yaml.safe_load(result.stdout) or []

        evidence = []

        for post in posts[:limit]:
            evidence.append(
                {
                    "external_id": str(post.get("id")),
                    "title": post.get("title", ""),
                    "content": post.get("text", ""),
                    "url": post.get("url", ""),
                    "author": post.get("author", ""),
                    "published_at": post.get("created_at"),
                    "metadata": {
                        "subreddit": post.get("subreddit"),
                        "score": post.get("score"),
                    },
                }
            )

        return evidence

    def collect(self, *args, **kwargs):
        return self.fetch(*args, **kwargs)