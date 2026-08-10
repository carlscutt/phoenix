import subprocess


def collect(command: list[str]) -> subprocess.CompletedProcess:
    """
    Execute an Agent Reach (or upstream) command and return the result.

    This is intentionally a very thin wrapper around subprocess.run().
    """

    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
    )