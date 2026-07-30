"""
Live smoke test for RedditCollector — hits the real Reddit API.
Run manually, not part of CI (depends on external network + Reddit's
availability/rate limits).
"""
from projects.phoenix.collectors.reddit_collector import RedditCollector

def main():
    collector = RedditCollector()
    results = collector.fetch("recruitment complaints", max_results=5)

    print(f"Got {len(results)} results\n")
    for r in results:
        print(f"[{r.source_type}] {r.source_url}")
        print(f"  snippet: {r.raw_snippet[:120]}...")
        print(f"  extra: {r.extra}")
        print()

    assert len(results) > 0, "expected at least one result for a common topic"
    assert all(r.source_url.startswith("https://www.reddit.com") for r in results)
    print("SMOKE TEST PASSED")

if __name__ == "__main__":
    main()