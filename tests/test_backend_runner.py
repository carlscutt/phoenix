import shutil

from integrations.backend_runner import run


def test_can_execute_agent_reach():
    executable = shutil.which("agent-reach")

    assert executable is not None

    result = run([executable, "version"])

    assert result.returncode == 0

    assert result.stdout.strip() != ""