import json
import shutil
import subprocess

from .exceptions import (
    AgentReachExecutionError,
    AgentReachNotInstalledError,
)


def find_executable() -> str:
    executable = shutil.which("agent-reach")

    if executable is None:
        raise AgentReachNotInstalledError(
            "agent-reach executable was not found on PATH."
        )

    return executable


def run(*args: str) -> subprocess.CompletedProcess:
    executable = find_executable()

    result = subprocess.run(
        [executable, *args],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise AgentReachExecutionError(result.stderr.strip())

    return result


def doctor() -> dict:
    """
    Return the full Agent Reach doctor report.
    """
    result = run("doctor", "--json")
    return json.loads(result.stdout)


def doctor_json() -> dict:
    return doctor()


def get_status() -> dict:
    return doctor()


def get_active_backends() -> dict:
    """
    Return a mapping of platform -> active backend.

    Example:

    {
        "reddit": "OpenCLI",
        "twitter": "twitter-cli",
        "youtube": "yt-dlp",
    }
    """

    report = doctor()

    active = {}

    for platform, info in report.items():
        backend = info.get("active_backend")

        if backend:
            active[platform] = backend

    return active