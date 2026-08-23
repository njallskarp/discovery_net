"""Repository contracts and bundled persistence adapters."""

from discovery_net.repositories.json_file import JsonUnitOfWork
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
    "JsonUnitOfWork",
    "ReputationRepository",
    "ReviewAssignmentRepository",
    "ReviewPolicyRepository",
    "ReviewRepository",
    "UnitOfWork",
]
