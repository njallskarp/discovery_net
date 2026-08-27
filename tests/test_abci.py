from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2 as abci
from discovery_net.knowledge_graph import Contribution, ContributionKind
from discovery_net.node import (
    ArtifactLedgerSnapshot,
    CometBFTABCIAdapter,
    CometBFTCallbackHandler,
    LocalArtifactLedger,
    TransactionCode,
    TransactionValidator,
)
from discovery_net.wire import (
    TRANSACTION_LIMITS,
    encode_transaction,
    sign_artifact,
    sign_transaction,
)

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


@dataclass(slots=True)
class MemoryArtifactLedgerStore:
    snapshot: ArtifactLedgerSnapshot | None = None

    def load(self) -> ArtifactLedgerSnapshot | None:
        return self.snapshot

    def save(self, snapshot: ArtifactLedgerSnapshot) -> None:
        self.snapshot = snapshot


def adapter(
    store: MemoryArtifactLedgerStore | None = None,
) -> tuple[CometBFTABCIAdapter, MemoryArtifactLedgerStore]:
    ledger_store = store if store is not None else MemoryArtifactLedgerStore()
    handler = CometBFTCallbackHandler(
        validator=TransactionValidator(expected_chain_id=CHAIN_ID),
        store=ledger_store,
    )
    return CometBFTABCIAdapter(handler=handler), ledger_store


def transaction(title: str) -> bytes:
    contribution = Contribution(
        kind=ContributionKind.PROBLEM_STATEMENT,
        title=title,
        body=f"Body for {title}",
        created_at=datetime(2026, 8, 25, 12, tzinfo=UTC),
    )
    envelope = sign_artifact(
        chain_id=CHAIN_ID,
        artifact=contribution,
        private_key=PRIVATE_KEY,
    )
    return encode_transaction(
        sign_transaction(
            envelopes=(envelope,),
            private_key=PRIVATE_KEY,
        )
    )


def test_bindings_preserve_the_cometbft_v040_abci_contract() -> None:
    service = abci.DESCRIPTOR.services_by_name["ABCI"]

    assert service.full_name == "tendermint.abci.ABCI"
    assert abci.RequestCheckTx.DESCRIPTOR.fields_by_name["tx"].number == 1
    assert abci.RequestFinalizeBlock.DESCRIPTOR.fields_by_name["txs"].number == 1
    assert abci.RequestFinalizeBlock.DESCRIPTOR.fields_by_name["height"].number == 5
    assert abci.ResponseFinalizeBlock.DESCRIPTOR.fields_by_name["tx_results"].number == 2
    assert abci.ResponseFinalizeBlock.DESCRIPTOR.fields_by_name["app_hash"].number == 5


def test_info_reports_only_committed_state() -> None:
    application, _ = adapter()
    initial_hash = LocalArtifactLedger().state_hash()

    assert application.info(abci.RequestInfo()) == abci.ResponseInfo(
        last_block_height=0,
        last_block_app_hash=initial_hash,
    )

    finalized = application.finalize_block(
        abci.RequestFinalizeBlock(height=1, txs=(transaction("First"),))
    )

    assert application.info(abci.RequestInfo()) == abci.ResponseInfo(
        last_block_height=0,
        last_block_app_hash=initial_hash,
    )

    application.commit(abci.RequestCommit())

    assert application.info(abci.RequestInfo()) == abci.ResponseInfo(
        last_block_height=1,
        last_block_app_hash=finalized.app_hash,
    )


def test_info_recovers_the_last_persisted_height_and_hash() -> None:
    first_application, store = adapter()
    finalized = first_application.finalize_block(
        abci.RequestFinalizeBlock(height=1, txs=(transaction("First"),))
    )
    first_application.commit(abci.RequestCommit())

    recovered_application, _ = adapter(store)

    assert recovered_application.info(abci.RequestInfo()) == abci.ResponseInfo(
        last_block_height=1,
        last_block_app_hash=finalized.app_hash,
    )


def test_init_chain_returns_the_validated_initial_app_hash() -> None:
    application, store = adapter()

    response = application.init_chain(
        abci.RequestInitChain(
            chain_id=CHAIN_ID,
            initial_height=1,
        )
    )

    assert response == abci.ResponseInitChain(app_hash=LocalArtifactLedger().state_hash())
    assert store.snapshot is None


def test_init_chain_rejects_a_different_chain() -> None:
    application, _ = adapter()

    with pytest.raises(ValueError, match="configured chain"):
        application.init_chain(
            abci.RequestInitChain(
                chain_id="discovery-net-mainnet",
                initial_height=1,
            )
        )


def test_check_tx_maps_validation_code_without_changing_state() -> None:
    application, store = adapter()
    encoded = transaction("First")

    accepted = application.check_tx(abci.RequestCheckTx(tx=encoded))
    invalid = application.check_tx(abci.RequestCheckTx(tx=b"not-an-envelope"))

    assert accepted == abci.ResponseCheckTx(code=TransactionCode.ACCEPTED)
    assert invalid == abci.ResponseCheckTx(code=TransactionCode.INVALID_TRANSACTION)
    assert store.snapshot is None


def test_prepare_proposal_preserves_the_prefix_that_fits() -> None:
    application, store = adapter()
    transactions = (b"one", b"12345", b"x")

    response = application.prepare_proposal(
        abci.RequestPrepareProposal(
            max_tx_bytes=8,
            txs=transactions,
        )
    )

    assert tuple(response.txs) == transactions[:2]
    assert store.snapshot is None


def test_process_proposal_returns_an_explicit_deterministic_acceptance() -> None:
    application, store = adapter()

    response = application.process_proposal(
        abci.RequestProcessProposal(
            height=1,
            txs=(b"not-an-envelope",),
        )
    )

    assert response.status == abci.ResponseProcessProposal.ACCEPT
    assert store.snapshot is None


def test_finalize_block_preserves_transaction_order_and_returns_app_hash() -> None:
    application, store = adapter()
    first = transaction("First")
    second = transaction("Second")

    response = application.finalize_block(
        abci.RequestFinalizeBlock(
            height=1,
            txs=(first, b"not-an-envelope", first, second),
        )
    )

    assert tuple(result.code for result in response.tx_results) == (
        TransactionCode.ACCEPTED,
        TransactionCode.INVALID_TRANSACTION,
        TransactionCode.DUPLICATE,
        TransactionCode.ACCEPTED,
    )
    assert len(response.app_hash) == 32
    assert store.snapshot is None
    assert abci.ResponseFinalizeBlock.FromString(response.SerializeToString()) == response


def test_finalize_block_rejects_an_oversized_transaction_that_bypassed_check_tx() -> None:
    application, store = adapter()
    oversized = bytes(TRANSACTION_LIMITS.maximum_encoded_bytes + 1)

    proposal = application.process_proposal(abci.RequestProcessProposal(height=1, txs=(oversized,)))
    finalized = application.finalize_block(abci.RequestFinalizeBlock(height=1, txs=(oversized,)))
    application.commit(abci.RequestCommit())

    assert proposal.status == abci.ResponseProcessProposal.ACCEPT
    assert tuple(result.code for result in finalized.tx_results) == (
        TransactionCode.TRANSACTION_TOO_LARGE,
    )
    assert finalized.app_hash == LocalArtifactLedger().state_hash()
    assert store.snapshot == ArtifactLedgerSnapshot(height=1, entries=())


def test_commit_persists_before_returning_an_acknowledgement() -> None:
    application, store = adapter()
    application.finalize_block(abci.RequestFinalizeBlock(height=1, txs=(transaction("First"),)))

    response = application.commit(abci.RequestCommit())

    assert response == abci.ResponseCommit()
    assert store.snapshot is not None
    assert store.snapshot.height == 1
    assert len(store.snapshot.entries) == 1


@pytest.mark.parametrize(
    ("method_name", "message", "expected_type"),
    [
        ("info", abci.RequestCommit(), "RequestInfo"),
        ("init_chain", abci.RequestInfo(), "RequestInitChain"),
        ("check_tx", abci.RequestInfo(), "RequestCheckTx"),
        ("prepare_proposal", abci.RequestCheckTx(), "RequestPrepareProposal"),
        ("process_proposal", abci.RequestPrepareProposal(), "RequestProcessProposal"),
        ("finalize_block", abci.RequestCheckTx(), "RequestFinalizeBlock"),
        ("commit", abci.RequestFinalizeBlock(), "RequestCommit"),
    ],
)
def test_adapter_rejects_the_wrong_request_message(
    method_name: str,
    message: object,
    expected_type: str,
) -> None:
    application, _ = adapter()

    with pytest.raises(TypeError, match=expected_type):
        getattr(application, method_name)(message)
