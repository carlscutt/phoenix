"""
RSS Collector

Collects articles from RSS feeds and returns raw evidence dictionaries.
"""

from __future__ import annotations

import feedparser

from agent_reach.base import BaseCollector


class RSSCollector(BaseCollector):

    name = "RSS"

    version = "1.0"

    enabled = True

    def __init__(self, feeds: list[str]) -> None:
        self.feeds = feeds

    def collect(self) -> list[dict]:

        results = []

        for url in self.feeds:

            feed = feedparser.parse(url)

            for entry in feed.entries:

                results.append(
                    {
                        "external_id": entry.get("id", entry.get("link")),
                        "title": entry.get("title", ""),
                        "content": entry.get("summary", ""),
                        "url": entry.get("link", ""),
                        "author": entry.get("author"),
                        "published_at": entry.get("published"),
                        "metadata": {
                            "feed": feed.feed.get("title", ""),
                        },
                    }
                )

        return results