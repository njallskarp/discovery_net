# Verifies genesis governance reaches CometBFT and persists atomically with block state.

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
    SignedValidatorSetChange,
    ValidatorMembershipChange,
    ValidatorMembershipOperation,
    ValidatorSetChange,
    approve_validator_set_change,
    encode_validator_set_change,
)

CHAIN_ID = "discovery-governance-test"
GOVERNANCE_KEYS = tuple(
    Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32) for value in (1, 2, 3)
)
VALIDATOR_KEYS = tuple(
    Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32) for value in (11, 12)
)


def public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def signed_addition() -> SignedValidatorSetChange:
    change = ValidatorSetChange(
        chain_id=CHAIN_ID,
        sequence=1,
        changes=(
            ValidatorMembershipChange(
                public_key=public_key(VALIDATOR_KEYS[1]),
                operation=ValidatorMembershipOperation.ADD,
            ),
        ),
    )
    return SignedValidatorSetChange(
        change=change,
        approvals=tuple(
            sorted(
                (
                    approve_validator_set_change(change, private_key)
                    for private_key in GOVERNANCE_KEYS[:2]
                ),
                key=lambda approval: approval.signer_public_key,
            )
        ),
    )


def genesis_state() -> bytes:
    governance = ValidatorGovernanceConfig(
        member_public_keys=tuple(sorted(public_key(key) for key in GOVERNANCE_KEYS)),
        approval_threshold=2,
        validator_power=10,
    ).initial_state(validator_public_keys=(public_key(VALIDATOR_KEYS[0]),))
    return encode_genesis_application_state(governance)


def application(path: Path) -> CometBFTABCIAdapter:
    return CometBFTABCIAdapter(
        handler=CometBFTCallbackHandler(
            validator=TransactionValidator(expected_chain_id=CHAIN_ID),
            store=SQLiteApplicationStateStore(path=path),
        )
    )


def test_governed_validator_addition_survives_commit_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "application.sqlite3"
    first = application(path)
    initial = first.init_chain(
        abci.RequestInitChain(
            chain_id=CHAIN_ID,
            initial_height=1,
            app_state_bytes=genesis_state(),
            validators=(
                abci.ValidatorUpdate(
                    pub_key=crypto.PublicKey(ed25519=public_key(VALIDATOR_KEYS[0])),
                    power=10,
                ),
            ),
        )
    )
    transaction = encode_validator_set_change(signed_addition())

    assert first.check_tx(abci.RequestCheckTx(tx=transaction)).code == TransactionCode.ACCEPTED
    finalized = first.finalize_block(abci.RequestFinalizeBlock(height=1, txs=(transaction,)))

    assert tuple(result.code for result in finalized.tx_results) == (TransactionCode.ACCEPTED,)
    assert len(finalized.validator_updates) == 1
    assert finalized.validator_updates[0].pub_key.ed25519 == public_key(VALIDATOR_KEYS[1])
    assert finalized.validator_updates[0].power == 10
    assert finalized.app_hash != initial.app_hash
    first.commit(abci.RequestCommit())

    snapshot = SQLiteApplicationStateStore(path=path).load()
    assert snapshot is not None
    assert snapshot.height == 1
    assert snapshot.artifact_ledger.entries == ()
    assert snapshot.validator_governance is not None
    assert snapshot.validator_governance.sequence == 1
    assert snapshot.validator_governance.validator_public_keys == tuple(
        sorted((public_key(VALIDATOR_KEYS[0]), public_key(VALIDATOR_KEYS[1])))
    )

    recovered = application(path)
    assert recovered.info(abci.RequestInfo()).last_block_app_hash == finalized.app_hash
    assert (
        recovered.check_tx(abci.RequestCheckTx(tx=transaction)).code
        == TransactionCode.INVALID_SEQUENCE
    )


def test_governance_is_opt_in_and_legacy_application_hashes_are_unchanged(tmp_path: Path) -> None:
    legacy = application(tmp_path / "legacy.sqlite3")
    initial = legacy.init_chain(abci.RequestInitChain(chain_id=CHAIN_ID, initial_height=1))
    transaction = encode_validator_set_change(signed_addition())

    checked = legacy.check_tx(abci.RequestCheckTx(tx=transaction))
    finalized = legacy.finalize_block(abci.RequestFinalizeBlock(height=1, txs=()))

    assert checked.code == TransactionCode.GOVERNANCE_DISABLED
    assert finalized.app_hash == initial.app_hash
    assert tuple(finalized.validator_updates) == ()


def test_genesis_governance_must_match_cometbft_validator_membership(tmp_path: Path) -> None:
    governed = application(tmp_path / "mismatched.sqlite3")

    with pytest.raises(ValueError, match="does not match"):
        governed.init_chain(
            abci.RequestInitChain(
                chain_id=CHAIN_ID,
                initial_height=1,
                app_state_bytes=genesis_state(),
                validators=(
                    abci.ValidatorUpdate(
                        pub_key=crypto.PublicKey(ed25519=public_key(VALIDATOR_KEYS[1])),
                        power=10,
                    ),
                ),
            )
        )

    assert SQLiteApplicationStateStore(path=tmp_path / "mismatched.sqlite3").load() is None
