import subprocess

from .exceptions import BackendUnavailableError


def collect(command: list[str]) -> subprocess.CompletedProcess:
    """
    Execute an Agent Reach (or upstream) command and return the result.

    This is intentionally a very thin wrapper around subprocess.run().
    """

    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise BackendUnavailableError(
            f"Backend executable not found: {command[0]}"
        ) from exc
