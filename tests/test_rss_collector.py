import pytest

from collectors.rss import RSSCollector
from integrations.agent_reach.exceptions import BackendUnavailableError


def test_collect_returns_list():
    collector = RSSCollector()

    evidence = collector.fetch(
        "https://hnrss.org/frontpage"
    )

    assert isinstance(evidence, list)


def test_collect_requires_agent_reach_rss_backend(monkeypatch):
    monkeypatch.setattr(
        "collectors.rss.doctor",
        lambda: {"rss": {"active_backend": None}},
    )

    collector = RSSCollector()

    with pytest.raises(BackendUnavailableError):
        collector.fetch("https://hnrss.org/frontpage")
