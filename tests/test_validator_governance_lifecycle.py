# Verifies governance state and delayed CometBFT updates survive real application commits.

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2 as abci
from discovery_net._cometbft.v0_40.tendermint.crypto import keys_pb2 as crypto
from discovery_net.node import (
    CometBFTABCIAdapter,
    CometBFTCallbackHandler,
    SQLiteApplicationStateStore,
    TransactionCode,
    TransactionValidator,
    ValidatorGovernanceConfig,
)
from discovery_net.node.validator_governance_codec import encode_genesis_application_state
from discovery_net.wire import (
    ValidatorMembershipOperation,
    ValidatorMembershipProposal,
    ValidatorOperator,
    approve_validator_proposal,
    encode_validator_governance_transaction,
    nominate_validator,
    propose_validator_membership,
    validator_proposal_id,
)

CHAIN_ID = "discovery-governance-test"


def _key(value: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32)


CONSENSUS_KEYS = tuple(_key(value) for value in (11, 12, 13, 14))
GOVERNANCE_KEYS = tuple(_key(value) for value in (31, 32, 33, 34))


def _public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _operators() -> tuple[ValidatorOperator, ...]:
    return tuple(
        sorted(
            (
                ValidatorOperator(
                    consensus_public_key=_public_key(CONSENSUS_KEYS[index]),
                    governance_public_key=_public_key(GOVERNANCE_KEYS[index]),
                )
                for index in range(3)
            ),
            key=lambda value: value.consensus_public_key,
        )
    )


def _governance_key(public_key: bytes) -> Ed25519PrivateKey:
    return next(key for key in GOVERNANCE_KEYS if _public_key(key) == public_key)


def _proposal() -> ValidatorMembershipProposal:
    nomination = nominate_validator(
        chain_id=CHAIN_ID,
        consensus_private_key=CONSENSUS_KEYS[3],
        governance_private_key=GOVERNANCE_KEYS[3],
    )
    sponsor = _operators()[0]
    return propose_validator_membership(
        chain_id=CHAIN_ID,
        operation=ValidatorMembershipOperation.ADD,
        operator=nomination.operator,
        sponsor_private_key=_governance_key(sponsor.governance_public_key),
        nomination=nomination,
    )


def _genesis_state() -> bytes:
    return encode_genesis_application_state(
        ValidatorGovernanceConfig(operators=_operators(), validator_power=10).initial_state()
    )


def test_genesis_accepts_cometbft_json_formatting(tmp_path: Path) -> None:
    application = _application(tmp_path / "formatted-genesis.sqlite3")
    formatted_state = json.dumps(json.loads(_genesis_state()), indent=2).encode()

    initialized = application.init_chain(
        abci.RequestInitChain(
            chain_id=CHAIN_ID,
            initial_height=1,
            app_state_bytes=formatted_state,
            validators=tuple(
                abci.ValidatorUpdate(
                    pub_key=crypto.PublicKey(ed25519=operator.consensus_public_key),
                    power=10,
                )
                for operator in _operators()
            ),
        )
    )

    assert initialized.app_hash


def test_artifact_only_store_cannot_advance_a_governed_ledger(tmp_path: Path) -> None:
    path = tmp_path / "governed.sqlite3"
    application = _application(path)
    _initialize(application)
    store = SQLiteApplicationStateStore(path=path)
    snapshot = store.load()
    assert snapshot is not None

    with pytest.raises(ValueError, match="artifact-only writes are disabled"):
        store.save_artifact_ledger(snapshot.artifact_ledger)


def _application(path: Path) -> CometBFTABCIAdapter:
    return CometBFTABCIAdapter(
        handler=CometBFTCallbackHandler(
            validator=TransactionValidator(expected_chain_id=CHAIN_ID),
            store=SQLiteApplicationStateStore(path=path),
        )
    )


def _initialize(application: CometBFTABCIAdapter) -> None:
    application.init_chain(
        abci.RequestInitChain(
            chain_id=CHAIN_ID,
            initial_height=1,
            app_state_bytes=_genesis_state(),
            validators=tuple(
                abci.ValidatorUpdate(
                    pub_key=crypto.PublicKey(ed25519=operator.consensus_public_key),
                    power=10,
                )
                for operator in _operators()
            ),
        )
    )


def _finalize_and_commit(
    application: CometBFTABCIAdapter,
    *,
    height: int,
    transactions: tuple[bytes, ...] = (),
) -> abci.ResponseFinalizeBlock:
    finalized = application.finalize_block(
        abci.RequestFinalizeBlock(height=height, txs=transactions)
    )
    application.commit(abci.RequestCommit())
    return finalized


def test_async_admission_persists_and_activates_after_the_cometbft_delay(
    tmp_path: Path,
) -> None:
    path = tmp_path / "application.sqlite3"
    application = _application(path)
    _initialize(application)
    proposal = _proposal()
    proposal_bytes = encode_validator_governance_transaction(proposal)

    first = _finalize_and_commit(application, height=1, transactions=(proposal_bytes,))
    assert tuple(result.code for result in first.tx_results) == (TransactionCode.ACCEPTED,)
    assert tuple(first.validator_updates) == ()

    application = _application(path)
    persisted = SQLiteApplicationStateStore(path=path).load()
    assert persisted is not None and persisted.validator_governance is not None
    state = persisted.validator_governance
    assert len(state.proposals) == 1
    remaining = tuple(
        operator
        for operator in state.operators
        if operator.governance_public_key != proposal.sponsor_public_key
    )

    first_approval = approve_validator_proposal(
        chain_id=CHAIN_ID,
        proposal_id=validator_proposal_id(proposal),
        private_key=_governance_key(remaining[0].governance_public_key),
    )
    second = _finalize_and_commit(
        application,
        height=2,
        transactions=(encode_validator_governance_transaction(first_approval),),
    )
    assert tuple(second.validator_updates) == ()

    second_approval = approve_validator_proposal(
        chain_id=CHAIN_ID,
        proposal_id=validator_proposal_id(proposal),
        private_key=_governance_key(remaining[1].governance_public_key),
    )
    third = _finalize_and_commit(
        application,
        height=3,
        transactions=(encode_validator_governance_transaction(second_approval),),
    )
    assert len(third.validator_updates) == 1
    assert third.validator_updates[0].pub_key.ed25519 == proposal.operator.consensus_public_key
    assert third.validator_updates[0].power == 10

    fourth = _finalize_and_commit(application, height=4)
    assert tuple(fourth.validator_updates) == ()
    snapshot = SQLiteApplicationStateStore(path=path).load()
    assert snapshot is not None and snapshot.validator_governance is not None
    assert len(snapshot.validator_governance.operators) == 3

    _finalize_and_commit(application, height=5)
    recovered = _application(path)
    snapshot = SQLiteApplicationStateStore(path=path).load()
    assert snapshot is not None and snapshot.validator_governance is not None
    assert len(snapshot.validator_governance.operators) == 4
    assert proposal.operator in snapshot.validator_governance.operators
    assert recovered.info(abci.RequestInfo()).last_block_height == 5


def test_an_approval_cannot_bypass_committed_proposal_ordering(tmp_path: Path) -> None:
    application = _application(tmp_path / "same-block.sqlite3")
    _initialize(application)
    proposal = _proposal()
    approver = next(
        operator
        for operator in _operators()
        if operator.governance_public_key != proposal.sponsor_public_key
    )
    approval = approve_validator_proposal(
        chain_id=CHAIN_ID,
        proposal_id=validator_proposal_id(proposal),
        private_key=_governance_key(approver.governance_public_key),
    )

    finalized = _finalize_and_commit(
        application,
        height=1,
        transactions=(
            encode_validator_governance_transaction(proposal),
            encode_validator_governance_transaction(approval),
        ),
    )

    assert tuple(result.code for result in finalized.tx_results) == (
        TransactionCode.ACCEPTED,
        TransactionCode.UNKNOWN_VALIDATOR_PROPOSAL,
    )


def test_governance_is_opt_in_and_legacy_application_hashes_are_unchanged(
    tmp_path: Path,
) -> None:
    legacy = _application(tmp_path / "legacy.sqlite3")
    initial = legacy.init_chain(abci.RequestInitChain(chain_id=CHAIN_ID, initial_height=1))
    transaction = encode_validator_governance_transaction(_proposal())

    checked = legacy.check_tx(abci.RequestCheckTx(tx=transaction))
    finalized = legacy.finalize_block(abci.RequestFinalizeBlock(height=1, txs=()))

    assert checked.code == TransactionCode.GOVERNANCE_DISABLED
    assert finalized.app_hash == initial.app_hash
    assert tuple(finalized.validator_updates) == ()


def test_genesis_governance_must_match_cometbft_validator_membership(
    tmp_path: Path,
) -> None:
    governed = _application(tmp_path / "mismatched.sqlite3")

    with pytest.raises(ValueError, match="does not match"):
        governed.init_chain(
            abci.RequestInitChain(
                chain_id=CHAIN_ID,
                initial_height=1,
                app_state_bytes=_genesis_state(),
                validators=(
                    abci.ValidatorUpdate(
                        pub_key=crypto.PublicKey(ed25519=_public_key(CONSENSUS_KEYS[3])),
                        power=10,
                    ),
                ),
            )
        )

    assert SQLiteApplicationStateStore(path=tmp_path / "mismatched.sqlite3").load() is None
