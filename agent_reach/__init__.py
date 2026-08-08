from agent_reach.registry import registry
from agent_reach.runner import runner

from agent_reach.collectors.rss import RSSCollector
from agent_reach.collectors.github import GitHubCollector

registry.register(
    RSSCollector(
        [
            "https://hnrss.org/frontpage",
            "https://feeds.feedburner.com/oreilly/radar",
        ]
    )
)

registry.register(
    GitHubCollector()
)