"""Distinct static types for locally assigned artifact identifiers."""

from typing import NewType

AgentId = NewType("AgentId", str)
KeyId = NewType("KeyId", str)
ContributionId = NewType("ContributionId", str)
RelationId = NewType("RelationId", str)
ReviewAssignmentId = NewType("ReviewAssignmentId", str)
ReviewId = NewType("ReviewId", str)
ReputationEventId = NewType("ReputationEventId", str)
