from agent_reach.runner import runner

items = runner.run()

print()
print(f"Collected {len(items)} items")
print()

for item in items[:10]:
    print(item)