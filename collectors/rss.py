from __future__ import annotations

import feedparser

from phoenix.collectors.base import BaseCollector
from phoenix.integrations.agent_reach.adapter import doctor
from phoenix.integrations.agent_reach.exceptions import BackendUnavailableError


class RSSCollector(BaseCollector):
    name = "RSS"
    version = "2.0"
    enabled = True

    def fetch(
        self,
        feed_url: str,
        limit: int = 25,
    ) -> list[dict]:
        """
        Collect RSS evidence using the RSS backend provisioned by Agent Reach.

        Agent Reach owns backend availability; Phoenix performs only the
        feed parsing and evidence mapping because the supported Agent Reach
        RSS backend is feedparser itself.
        """

        status = doctor()
        backend = status["rss"]["active_backend"]

        if backend != "feedparser":
            raise BackendUnavailableError(
                "No RSS feedparser backend is currently provisioned by Agent Reach."
            )

        feed = feedparser.parse(feed_url)

        evidence: list[dict] = []

        for entry in feed.entries[:limit]:
            evidence.append(
                {
                    "external_id": entry.get("id", entry.get("link", "")),
                    "title": entry.get("title", ""),
                    "content": entry.get("summary", ""),
                    "url": entry.get("link", ""),
                    "author": entry.get("author", ""),
                    "published_at": entry.get("published", ""),
                    "metadata": {
                        "tags": [
                            tag.get("term")
                            for tag in entry.get("tags", [])
                        ]
                    },
                }
            )

        return evidence
