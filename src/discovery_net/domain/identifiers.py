"""Distinct static types for locally assigned artifact identifiers."""

from typing import NewType

AgentId = NewType("AgentId", str)
ContributionId = NewType("ContributionId", str)
RelationId = NewType("RelationId", str)
