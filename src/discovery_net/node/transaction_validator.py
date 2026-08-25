# Validates encoded network transactions without changing node state.

from dataclasses import dataclass
from typing import Protocol

from discovery_net.knowledge_graph import ArtifactRef
from discovery_net.node.cometbft_callback_handler import TransactionCode, TransactionResult
from discovery_net.wire import (
    CodecError,
    artifact_ref,
    decode_envelope,
    verify_envelope,
)


class _ArtifactLookup(Protocol):
    def contains(self, artifact_ref: ArtifactRef) -> bool: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionValidator:
    """Validates transactions against one network and its committed artifacts."""

    expected_network_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.expected_network_id, str):
            raise TypeError("expected_network_id must be a string")
        if not self.expected_network_id.strip():
            raise ValueError("expected_network_id must not be blank")

    def validate(
        self,
        transaction: bytes,
        artifacts: _ArtifactLookup,
    ) -> TransactionResult:
        """Return a deterministic result without modifying committed state."""

        try:
            envelope = decode_envelope(transaction)
        except (CodecError, TypeError):
            return TransactionResult(code=TransactionCode.INVALID_ENVELOPE)

        if envelope.network_id != self.expected_network_id:
            return TransactionResult(code=TransactionCode.WRONG_NETWORK)
        if not verify_envelope(envelope):
            return TransactionResult(code=TransactionCode.INVALID_SIGNATURE)
        if artifacts.contains(artifact_ref(envelope)):
            return TransactionResult(code=TransactionCode.DUPLICATE)
        return TransactionResult(code=TransactionCode.ACCEPTED)
