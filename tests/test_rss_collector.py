from collectors.rss import RSSCollector


def test_collect_returns_list():
    collector = RSSCollector()

    evidence = collector.fetch(
        "https://hnrss.org/frontpage"
    )

    assert isinstance(evidence, list)