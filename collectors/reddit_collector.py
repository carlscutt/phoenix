"""
Reddit collector — the only active collector in Module 1 v1, per the
approved architecture decisions (GitHub/YouTube/LinkedIn/Product
Hunt/Reviews/Forums all deferred).

Uses OAuth via PRAW (Reddit's official Python client), against
`oauth.reddit.com`. The unauthenticated public search endpoint
(`www.reddit.com/search.json`) was tried first and confirmed (2026-07-24,
live test) to hard-block with a bot-detection HTML challenge page
regardless of User-Agent — not a soft rate limit, a genuine wall. OAuth
is the only reliable path to Reddit's public data now.

Credentials load from environment variables — per the approved
decision, via a gitignored `.env` file, never hardcoded, never
committed:
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USER_AGENT     (optional — sensible default provided)

To obtain credentials: register a "script" app at
https://www.reddit.com/prefs/apps. No username/password is needed —
this uses PRAW's application-only (client-credentials) auth, which is
read-only and sufficient for public search. See `.env.example` in this
directory for the expected format.
"""
from __future__ import annotations

import os
from typing import Any

import praw
from dotenv import load_dotenv

from phoenix.collectors.base import BaseCollector, RawEvidence

load_dotenv()

DEFAULT_USER_AGENT = "phoenix-opportunity-discovery/0.1"
MAX_RESULTS_CAP = 100
MAX_SNIPPET_CHARS = 2000


class RedditCredentialsError(RuntimeError):
    """Raised when required Reddit OAuth credentials aren't set."""


def _load_credentials() -> tuple[str, str, str]:
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", DEFAULT_USER_AGENT)

    missing = [
        name
        for name, value in [
            ("REDDIT_CLIENT_ID", client_id),
            ("REDDIT_CLIENT_SECRET", client_secret),
        ]
        if not value
    ]
    if missing:
        raise RedditCredentialsError(
            "Missing required Reddit OAuth credentials: "
            f"{', '.join(missing)}. Set them in a .env file "
            "(see .env.example) or as environment variables. Register a "
            "script app at https://www.reddit.com/prefs/apps to obtain "
            "a client_id/client_secret."
        )
    return client_id, client_secret, user_agent


class RedditCollector(BaseCollector):
    source_type = "reddit"

    def __init__(self, reddit: "praw.Reddit | None" = None) -> None:
        """Pass an already-constructed `praw.Reddit` instance for
        testing; otherwise credentials are loaded from the environment
        and a real (read-only, application-only) client is built."""
        if reddit is not None:
            self._reddit = reddit
        else:
            client_id, client_secret, user_agent = _load_credentials()
            self._reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )

    def fetch(self, query: str, max_results: int = 50) -> list[RawEvidence]:
        if not query or not query.strip():
            raise ValueError("query is required and cannot be empty")

        limit = min(max_results, MAX_RESULTS_CAP)

        evidence: list[RawEvidence] = []
        try:
            submissions = self._reddit.subreddit("all").search(
                query, limit=limit, sort="relevance"
            )
            for submission in submissions:
                raw = self._to_raw_evidence(submission)
                if raw is not None:
                    evidence.append(raw)
        except (RedditCredentialsError, ValueError):
            raise
        except Exception as exc:
            raise RuntimeError(f"Reddit fetch failed for query {query!r}: {exc}") from exc

        return evidence

    def _to_raw_evidence(self, submission: Any) -> RawEvidence | None:
        permalink = getattr(submission, "permalink", None)
        if not permalink:
            return None

        title = (getattr(submission, "title", "") or "").strip()
        selftext = (getattr(submission, "selftext", "") or "").strip()
        snippet = f"{title}\n\n{selftext}".strip() if selftext else title
        if not snippet:
            return None
        snippet = snippet[:MAX_SNIPPET_CHARS]

        subreddit = getattr(submission, "subreddit", None)
        subreddit_name = getattr(subreddit, "display_name", None) if subreddit else None

        return RawEvidence(
            source_type=self.source_type,
            source_url=f"https://www.reddit.com{permalink}",
            raw_snippet=snippet,
            extra={
                "subreddit": subreddit_name,
                "score": getattr(submission, "score", None),
                "num_comments": getattr(submission, "num_comments", None),
                "created_utc": getattr(submission, "created_utc", None),
            },
        )
