import subprocess
from typing import Sequence


class BackendExecutionError(RuntimeError):
    """Raised when an external backend command fails."""


def run(command: Sequence[str]) -> subprocess.CompletedProcess:
    """
    Execute an external backend command.

    Returns the CompletedProcess object unchanged.
    """

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise BackendExecutionError(
            result.stderr.strip() or f"{command[0]} exited with {result.returncode}"
        )

    return result