"""Provider boundary. Production remains explicitly disabled until configured."""

from app.agent.contracts import AgentDecision


class DisabledProvider:
    name = "disabled"

    def decide(self, context, tool_schemas):
        return AgentDecision(kind="final", reason="MODEL_DISABLED")


class ScriptedProvider:
    """Test-only deterministic provider for exercising the harness."""

    name = "scripted"

    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def decide(self, context, tool_schemas):
        return next(self.decisions, AgentDecision(kind="final", reason="SCRIPT_COMPLETE"))
