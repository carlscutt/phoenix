import pytest

from integrations.agent_reach.evidence import collect
from integrations.agent_reach.exceptions import BackendUnavailableError


def test_missing_backend_raises():
    with pytest.raises(BackendUnavailableError):
        collect(["definitely-not-a-real-command"])