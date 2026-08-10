"""
Agent Reach integration exceptions.
"""


class AgentReachError(RuntimeError):
    """Base exception for Agent Reach integration."""


class AgentReachNotInstalledError(AgentReachError):
    """Agent Reach executable is not installed."""


class AgentReachExecutionError(AgentReachError):
    """Agent Reach command execution failed."""


class BackendUnavailableError(AgentReachError):
    """
    The backend required by a collector is not currently
    provisioned by Agent Reach.
    """