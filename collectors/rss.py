from __future__ import annotations

import feedparser

from collectors.base import BaseCollector


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
        Collect RSS evidence using the backend currently
        provisioned by Agent Reach.

        Agent Reach provisions feedparser.
        Phoenix only performs the mapping.
        """

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