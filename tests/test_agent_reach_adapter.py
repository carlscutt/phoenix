from integrations.agent_reach.adapter import (
    doctor_json,
    find_executable,
    get_active_backends,
    get_status,
)


def test_agent_reach_is_installed():
    executable = find_executable()
    assert executable.endswith("agent-reach")


def test_doctor_runs():
    report = doctor_json()

    assert isinstance(report, dict)
    assert len(report) > 0


def test_get_status():
    report = get_status()

    assert isinstance(report, dict)


def test_get_active_backends():
    backends = get_active_backends()

    assert isinstance(backends, dict)