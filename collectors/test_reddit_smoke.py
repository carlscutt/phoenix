"""
Live smoke test for the current Agent Reach-backed RedditCollector.

Run manually, not as part of CI. It depends on an installed and
authenticated Agent Reach Reddit backend.
"""

from collectors.reddit import RedditCollector


def main():
    collector = RedditCollector()
    results = collector.fetch("recruitment complaints", limit=5)

    print(f"Got {len(results)} results\n")

    for result in results:
        print(f"[{result.get('external_id')}] {result.get('url')}")
        print(f"  title: {result.get('title', '')}")
        print(f"  content: {result.get('content', '')[:120]}...")
        print(f"  metadata: {result.get('metadata', {})}")
        print()

    assert isinstance(results, list)
    assert all(
        result.get("url", "").startswith("https://www.reddit.com")
        for result in results
    )

    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
