# Signs and submits artifacts through a local CometBFT node.

from hashlib import sha256
from typing import final

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import ArtifactRef, Contribution, ContributionRelation
from discovery_net.submission._cometbft_rpc_client import _CometBFTRPCClient
from discovery_net.submission.incoming_relation import IncomingRelation
from discovery_net.submission.outgoing_relation import OutgoingRelation
from discovery_net.submission.submission_error import SubmissionError
from discovery_net.submission.submission_receipt import SubmissionReceipt
from discovery_net.wire import (
    TRANSACTION_LIMITS,
    SignedTransaction,
    TransactionLimitError,
    artifact_ref,
    encode_transaction,
    sign_artifact,
    sign_transaction,
)

type AttachedRelation = IncomingRelation | OutgoingRelation


@final
class ArtifactSubmitter:
    """Signs artifacts and asks a local CometBFT node to broadcast them."""

    __slots__ = ("_private_key", "_rpc_client")

    def __init__(
        self,
        *,
        private_key: Ed25519PrivateKey,
        cometbft_rpc_url: str,
    ) -> None:
        if not isinstance(private_key, Ed25519PrivateKey):
            raise TypeError("private_key must be an Ed25519PrivateKey")

        self._private_key = private_key
        self._rpc_client = _CometBFTRPCClient(url=cometbft_rpc_url)

    def submit_contribution(
        self,
        contribution: Contribution,
        *,
        relations: tuple[AttachedRelation, ...] = (),
    ) -> SubmissionReceipt:
        """Submit a contribution and its initial directed relations atomically."""
        if not isinstance(contribution, Contribution):
            raise TypeError("contribution must be a Contribution")
        if not isinstance(relations, tuple) or any(
            not isinstance(relation, (IncomingRelation, OutgoingRelation)) for relation in relations
        ):
            raise TypeError("relations must contain incoming or outgoing relations")
        _require_artifact_count(1 + len(relations))

        chain_id = self._rpc_client.fetch_chain_id()
        contribution_envelope = sign_artifact(
            chain_id=chain_id,
            artifact=contribution,
            private_key=self._private_key,
        )
        contribution_ref = artifact_ref(contribution_envelope)
        relation_envelopes = tuple(
            sign_artifact(
                chain_id=chain_id,
                artifact=_resolve_relation(
                    relation,
                    contribution_ref=contribution_ref,
                    contribution=contribution,
                ),
                private_key=self._private_key,
            )
            for relation in relations
        )
        return self._submit(
            sign_transaction(
                envelopes=(contribution_envelope, *relation_envelopes),
                private_key=self._private_key,
            )
        )

    def submit_relation(self, relation: ContributionRelation) -> SubmissionReceipt:
        """Submit a directed relation between existing contributions."""
        if not isinstance(relation, ContributionRelation):
            raise TypeError("relation must be a ContributionRelation")
        chain_id = self._rpc_client.fetch_chain_id()
        envelope = sign_artifact(
            chain_id=chain_id,
            artifact=relation,
            private_key=self._private_key,
        )
        return self._submit(sign_transaction(envelopes=(envelope,), private_key=self._private_key))

    def _submit(self, signed_transaction: SignedTransaction) -> SubmissionReceipt:
        transaction = encode_transaction(signed_transaction)
        try:
            TRANSACTION_LIMITS.require_artifact_count(len(signed_transaction.envelopes))
            TRANSACTION_LIMITS.require_encoded_size(transaction)
        except TransactionLimitError as error:
            raise SubmissionError(str(error)) from error
        response = self._rpc_client.broadcast_transaction(transaction)
        expected_hash = sha256(transaction).hexdigest().upper()
        if response.transaction_hash != expected_hash:
            raise SubmissionError("CometBFT returned a hash for a different transaction")
        return SubmissionReceipt(
            artifact_refs=tuple(
                artifact_ref(envelope) for envelope in signed_transaction.envelopes
            ),
            transaction_hash=response.transaction_hash,
            check_tx_code=response.check_tx_code,
        )


def _resolve_relation(
    relation: AttachedRelation,
    *,
    contribution_ref: ArtifactRef,
    contribution: Contribution,
) -> ContributionRelation:
    if isinstance(relation, OutgoingRelation):
        return ContributionRelation(
            from_contribution=contribution_ref,
            to_contribution=relation.to_contribution,
            kind=relation.kind,
            created_at=contribution.created_at,
        )
    return ContributionRelation(
        from_contribution=relation.from_contribution,
        to_contribution=contribution_ref,
        kind=relation.kind,
        created_at=contribution.created_at,
    )


def _require_artifact_count(artifact_count: int) -> None:
    try:
        TRANSACTION_LIMITS.require_artifact_count(artifact_count)
    except TransactionLimitError as error:
        raise SubmissionError(str(error)) from error
