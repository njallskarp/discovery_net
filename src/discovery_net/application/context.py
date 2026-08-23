"""Trusted identity passed from an authentication boundary."""

from dataclasses import dataclass

from discovery_net.domain import AgentId, KeyId


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentContext:
    """The authenticated agent and key responsible for an operation."""

    agent_id: AgentId
    key_id: KeyId

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("agent_id must not be blank")
        if not self.key_id.strip():
            raise ValueError("key_id must not be blank")
