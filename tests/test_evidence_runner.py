from integrations.agent_reach.evidence import collect


def test_collect_runs_agent_reach_help():
    result = collect(["agent-reach", "--help"])

    assert result.returncode == 0
    assert "doctor" in result.stdout