# Defines the immediate receipt returned after submitting a transaction.

from dataclasses import dataclass

from discovery_net.artifacts import ArtifactRef

_MAX_UINT32 = (1 << 32) - 1


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmissionReceipt:
    """Reports a local node's immediate response to an atomic transaction."""

    artifact_refs: tuple[ArtifactRef, ...]
    transaction_hash: str
    check_tx_code: int

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_refs, tuple):
            raise TypeError("artifact_refs must be a tuple")
        if not self.artifact_refs:
            raise ValueError("artifact_refs must not be empty")
        if any(not isinstance(reference, str) or not reference for reference in self.artifact_refs):
            raise ValueError("artifact_refs must contain nonblank references")
        if not isinstance(self.transaction_hash, str):
            raise TypeError("transaction_hash must be a string")
        if len(self.transaction_hash) != 64 or any(
            character not in "0123456789ABCDEF" for character in self.transaction_hash
        ):
            raise ValueError("transaction_hash must be 64 uppercase hexadecimal characters")
        if not isinstance(self.check_tx_code, int) or isinstance(self.check_tx_code, bool):
            raise TypeError("check_tx_code must be an integer")
        if not 0 <= self.check_tx_code <= _MAX_UINT32:
            raise ValueError("check_tx_code must be an unsigned 32-bit integer")

    @property
    def accepted(self) -> bool:
        """Return whether CheckTx accepted the transaction for broadcast."""
        return self.check_tx_code == 0
