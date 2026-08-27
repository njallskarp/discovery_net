# Defines deterministic resource limits for one network transaction.

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class TransactionLimit(StrEnum):
    """The protocol resource bound exceeded by a transaction."""

    ENCODED_BYTES = "encoded_bytes"
    ARTIFACT_COUNT = "artifact_count"


class TransactionLimitError(ValueError):
    """Raised when a transaction exceeds a deterministic protocol limit."""

    def __init__(self, limit: TransactionLimit, message: str) -> None:
        super().__init__(message)
        self.limit = limit


@dataclass(frozen=True, slots=True, kw_only=True)
class _TransactionLimits:
    """Enforces the network-wide resource bounds for one transaction."""

    maximum_encoded_bytes: int
    maximum_artifacts: int

    def require_encoded_size(self, transaction: bytes) -> None:
        """Reject transaction bytes larger than the protocol maximum."""
        if not isinstance(transaction, bytes):
            raise TypeError("transaction must be bytes")
        if len(transaction) > self.maximum_encoded_bytes:
            raise TransactionLimitError(
                TransactionLimit.ENCODED_BYTES,
                f"transaction exceeds {self.maximum_encoded_bytes} encoded bytes",
            )

    def require_artifact_count(self, artifact_count: int) -> None:
        """Reject an atomic package containing too many artifacts."""
        if not isinstance(artifact_count, int) or isinstance(artifact_count, bool):
            raise TypeError("artifact_count must be an integer")
        if artifact_count > self.maximum_artifacts:
            raise TransactionLimitError(
                TransactionLimit.ARTIFACT_COUNT,
                f"transaction exceeds {self.maximum_artifacts} artifacts",
            )


TRANSACTION_LIMITS: Final = _TransactionLimits(
    maximum_encoded_bytes=4 * 1024 * 1024,
    maximum_artifacts=256,
)
