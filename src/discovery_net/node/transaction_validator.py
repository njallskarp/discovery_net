# Validates encoded network transactions without changing node state.

from dataclasses import dataclass
from enum import IntEnum

from discovery_net.knowledge_graph import ArtifactRef, Contribution, ContributionRelation
from discovery_net.node.local_artifact_ledger import ArtifactLedgerLookup
from discovery_net.wire import (
    TRANSACTION_LIMITS,
    CodecError,
    TransactionLimitError,
    artifact_ref,
    decode_payload,
    decode_transaction,
    verify_transaction,
)


class TransactionCode(IntEnum):
    """Stable application codes returned to CometBFT for transactions."""

    ACCEPTED = 0
    INVALID_TRANSACTION = 1
    WRONG_CHAIN = 2
    INVALID_SIGNATURE = 3
    DUPLICATE = 4
    MISSING_REFERENCE = 5
    TRANSACTION_TOO_LARGE = 6
    TOO_MANY_ARTIFACTS = 7


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionResult:
    """The deterministic application result for one transaction."""

    code: TransactionCode


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
            TRANSACTION_LIMITS.require_encoded_size(transaction)
        except TransactionLimitError:
            return TransactionResult(code=TransactionCode.TRANSACTION_TOO_LARGE)
        except TypeError:
            return TransactionResult(code=TransactionCode.INVALID_TRANSACTION)

        try:
            signed_transaction = decode_transaction(transaction)
        except (CodecError, TypeError):
            return TransactionResult(code=TransactionCode.INVALID_TRANSACTION)

        try:
            TRANSACTION_LIMITS.require_artifact_count(len(signed_transaction.envelopes))
        except TransactionLimitError:
            return TransactionResult(code=TransactionCode.TOO_MANY_ARTIFACTS)

        if signed_transaction.chain_id != self.expected_chain_id:
            return TransactionResult(code=TransactionCode.WRONG_CHAIN)
        if not verify_transaction(signed_transaction):
            return TransactionResult(code=TransactionCode.INVALID_SIGNATURE)
        references = tuple(artifact_ref(envelope) for envelope in signed_transaction.envelopes)
        if len(set(references)) != len(references) or any(
            artifacts.envelope_by_ref(reference) is not None for reference in references
        ):
            return TransactionResult(code=TransactionCode.DUPLICATE)
        decoded_artifacts = tuple(
            decode_payload(envelope.payload_type, envelope.payload)
            for envelope in signed_transaction.envelopes
        )
        included_contributions = {
            reference
            for reference, artifact in zip(references, decoded_artifacts, strict=True)
            if isinstance(artifact, Contribution)
        }
        for artifact in decoded_artifacts:
            if isinstance(artifact, ContributionRelation) and (
                not _is_contribution(
                    artifact.from_contribution,
                    artifacts,
                    included_contributions,
                )
                or not _is_contribution(
                    artifact.to_contribution,
                    artifacts,
                    included_contributions,
                )
            ):
                return TransactionResult(code=TransactionCode.MISSING_REFERENCE)
        return TransactionResult(code=TransactionCode.ACCEPTED)


def _is_contribution(
    reference: ArtifactRef,
    artifacts: ArtifactLedgerLookup,
    included_contributions: set[ArtifactRef],
) -> bool:
    if reference in included_contributions:
        return True
    envelope = artifacts.envelope_by_ref(reference)
    if envelope is None:
        return False
    return isinstance(decode_payload(envelope.payload_type, envelope.payload), Contribution)
