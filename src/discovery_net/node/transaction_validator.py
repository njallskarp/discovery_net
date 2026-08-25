# Validates encoded network transactions without changing node state.

from dataclasses import dataclass

from discovery_net.node.cometbft_callback_handler import TransactionCode, TransactionResult
from discovery_net.node.local_artifact_ledger import ArtifactLedgerLookup
from discovery_net.wire import (
    CodecError,
    artifact_ref,
    decode_envelope,
    verify_envelope,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionValidator:
    """Validates transactions against one chain and its committed artifacts."""

    expected_chain_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.expected_chain_id, str):
            raise TypeError("expected_chain_id must be a string")
        if not self.expected_chain_id.strip():
            raise ValueError("expected_chain_id must not be blank")

    def validate(
        self,
        transaction: bytes,
        artifacts: ArtifactLedgerLookup,
    ) -> TransactionResult:
        """Return a deterministic result without modifying committed state."""

        try:
            envelope = decode_envelope(transaction)
        except (CodecError, TypeError):
            return TransactionResult(code=TransactionCode.INVALID_ENVELOPE)

        if envelope.chain_id != self.expected_chain_id:
            return TransactionResult(code=TransactionCode.WRONG_CHAIN)
        if not verify_envelope(envelope):
            return TransactionResult(code=TransactionCode.INVALID_SIGNATURE)
        if artifacts.contains(artifact_ref(envelope)):
            return TransactionResult(code=TransactionCode.DUPLICATE)
        return TransactionResult(code=TransactionCode.ACCEPTED)
