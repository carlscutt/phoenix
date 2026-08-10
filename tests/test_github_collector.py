from collectors.github import GitHubCollector


def test_collect_returns_list():
    collector = GitHubCollector()

    evidence = collector.fetch("ollama")

    assert isinstance(evidence, list)