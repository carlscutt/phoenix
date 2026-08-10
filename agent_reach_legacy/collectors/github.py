from __future__ import annotations

import requests

from agent_reach.base import BaseCollector


class GitHubCollector(BaseCollector):

    name = "GitHub"

    version = "1.0"

    enabled = True

    SEARCH = (
        "https://api.github.com/search/issues"
        "?q=is:issue+is:open+label:bug&sort=updated&order=desc&per_page=25"
    )

    def collect(self) -> list[dict]:

        response = requests.get(
            self.SEARCH,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Phoenix-Agent-Reach",
            },
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        results = []

        for issue in data.get("items", []):

            results.append(
                {
                    "external_id": str(issue["id"]),
                    "title": issue["title"],
                    "content": issue.get("body") or "",
                    "url": issue["html_url"],
                    "author": issue["user"]["login"],
                    "published_at": issue["created_at"],
                    "metadata": {
                        "repository": issue["repository_url"],
                        "state": issue["state"],
                    },
                }
            )

        return results