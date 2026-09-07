# Validates encoded network transactions without changing node state.

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from types import MappingProxyType

from discovery_net.artifacts import ArtifactRef
from discovery_net.artifacts.edge_revocation import EdgeRevocation
from discovery_net.domains.math.codec import MATH_DOMAIN
from discovery_net.node.authorization import can_revoke
from discovery_net.node.local_artifact_ledger import ArtifactLedgerLookup
from discovery_net.wire import (
    TRANSACTION_LIMITS,
    CodecError,
    PayloadType,
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
    UNAUTHORIZED_REVOCATION = 8
    INVALID_REVOCATION_TARGET = 9


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionResult:
    """The deterministic application result for one transaction."""

    code: TransactionCode


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionValidator:
    """Validates transactions against one chain and its committed artifacts."""

    expected_chain_id: str
    voting_power: Mapping[bytes, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.expected_chain_id, str):
            raise TypeError("expected_chain_id must be a string")
        if not self.expected_chain_id.strip():
            raise ValueError("expected_chain_id must not be blank")

        powers = dict(self.voting_power)
        for key, power in powers.items():
            if not isinstance(key, bytes) or len(key) != 32:
                raise ValueError("validator public key must be 32 bytes")
            if (
                not isinstance(power, int)
                or isinstance(power, bool)
                or not 0 <= power <= (1 << 63) - 1
            ):
                raise ValueError("validator voting power must be a nonnegative int64")
        object.__setattr__(self, "voting_power", MappingProxyType(powers))

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
            if not isinstance(artifact, EdgeRevocation) and MATH_DOMAIN.is_node(artifact)
        }
        for artifact in decoded_artifacts:
            if isinstance(artifact, EdgeRevocation):
                if not can_revoke(
                    signer_public_key=signed_transaction.signer_public_key,
                    voting_power=self.voting_power,
                ):
                    return TransactionResult(code=TransactionCode.UNAUTHORIZED_REVOCATION)
                target = artifacts.envelope_by_ref(artifact.target)
                if target is None:
                    return TransactionResult(code=TransactionCode.MISSING_REFERENCE)
                if target.payload_type is not PayloadType.CONTRIBUTION_RELATION:
                    return TransactionResult(code=TransactionCode.INVALID_REVOCATION_TARGET)
                continue
            if any(
                not _is_contribution(reference, artifacts, included_contributions)
                for reference in MATH_DOMAIN.references(artifact)
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
    artifact = decode_payload(envelope.payload_type, envelope.payload)
    return not isinstance(artifact, EdgeRevocation) and MATH_DOMAIN.is_node(artifact)
