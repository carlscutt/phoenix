
import pytest

from collectors.reddit import RedditCollector
from integrations.agent_reach.adapter import doctor
from integrations.agent_reach.exceptions import BackendUnavailableError


def test_collect_returns_list_when_backend_available():
    backend = doctor()["reddit"]["active_backend"]

    if backend is None:
        pytest.skip("No Reddit backend provisioned by Agent Reach.")

    collector = RedditCollector()

    evidence = collector.fetch("ollama")

    assert isinstance(evidence, list)


def test_collect_raises_when_backend_missing():
    backend = doctor()["reddit"]["active_backend"]

    if backend is not None:
        pytest.skip("A Reddit backend is installed.")

    collector = RedditCollector()

    with pytest.raises(BackendUnavailableError):
        collector.fetch("ollama")