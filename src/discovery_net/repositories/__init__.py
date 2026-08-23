"""Repository contracts and bundled persistence adapters."""

from discovery_net.repositories.memory import InMemoryUnitOfWork
from discovery_net.repositories.protocols import (
    ContributionRepository,
    ReputationRepository,
    ReviewAssignmentRepository,
    ReviewPolicyRepository,
    ReviewRepository,
    UnitOfWork,
)

__all__ = [
    "ContributionRepository",
    "InMemoryUnitOfWork",
    "ReputationRepository",
    "ReviewAssignmentRepository",
    "ReviewPolicyRepository",
    "ReviewRepository",
    "UnitOfWork",
]
