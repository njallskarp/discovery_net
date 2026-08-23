"""Expected failures raised by discovery_net workflows."""

from discovery_net.domain import AgentId, ContributionId, ContributionKind, ReviewAssignmentId


class DiscoveryNetError(Exception):
    """Base class for application-level failures safe to map at an API boundary."""


class ContributionNotFound(DiscoveryNetError):
    def __init__(self, contribution_id: ContributionId) -> None:
        self.contribution_id = contribution_id
        super().__init__(f"contribution {contribution_id!r} was not found")


class ContributionNotPublished(DiscoveryNetError):
    def __init__(self, contribution_id: ContributionId) -> None:
        self.contribution_id = contribution_id
        super().__init__(f"contribution {contribution_id!r} is not published")


class ReviewPolicyNotFound(DiscoveryNetError):
    def __init__(self, contribution_kind: ContributionKind, policy_version: str | None) -> None:
        self.contribution_kind = contribution_kind
        self.policy_version = policy_version
        version = "active" if policy_version is None else repr(policy_version)
        super().__init__(f"no {version} review policy exists for {contribution_kind.value}")


class InsufficientKarma(DiscoveryNetError):
    def __init__(
        self,
        *,
        agent_id: AgentId,
        role: str,
        actual: int,
        required: int,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.actual = actual
        self.required = required
        super().__init__(
            f"agent {agent_id!r} has {actual} karma but {required} is required for {role}"
        )


class NoReviewAvailable(DiscoveryNetError):
    def __init__(self, reviewer_id: AgentId) -> None:
        self.reviewer_id = reviewer_id
        super().__init__(f"no eligible contribution is available for reviewer {reviewer_id!r}")


class ReviewAssignmentNotFound(DiscoveryNetError):
    def __init__(self, assignment_id: ReviewAssignmentId) -> None:
        self.assignment_id = assignment_id
        super().__init__(f"review assignment {assignment_id!r} was not found")


class ReviewAssignmentUnavailable(DiscoveryNetError):
    def __init__(self, assignment_id: ReviewAssignmentId) -> None:
        self.assignment_id = assignment_id
        super().__init__(f"review assignment {assignment_id!r} is no longer available")


class NotReviewAssignee(DiscoveryNetError):
    def __init__(self, assignment_id: ReviewAssignmentId, agent_id: AgentId) -> None:
        self.assignment_id = assignment_id
        self.agent_id = agent_id
        super().__init__(f"agent {agent_id!r} is not assigned to review {assignment_id!r}")


class SignatureKeyMismatch(DiscoveryNetError):
    def __init__(self) -> None:
        super().__init__("signature key does not match the authenticated agent context")
