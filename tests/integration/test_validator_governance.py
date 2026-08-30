# Proves threshold governance changes the live CometBFT validator set without resetting history.

import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net.node.runtime import CometBFTValidatorProvisioner, ValidatorIdentity
from discovery_net.node.validator_governance import ValidatorGovernanceConfig
from discovery_net.wire import (
    SignedValidatorSetChange,
    ValidatorMembershipChange,
    ValidatorMembershipOperation,
    ValidatorSetChange,
    approve_validator_set_change,
    encode_validator_set_change,
)
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import signed_transaction

_VALIDATOR_SET_TIMEOUT_SECONDS = 20


def test_threshold_governance_adds_equal_validators_that_preserve_quorum(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    governance_keys = tuple(
        Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32) for value in (31, 32, 33)
    )
    governance = ValidatorGovernanceConfig(
        member_public_keys=tuple(sorted(_public_key(key) for key in governance_keys)),
        approval_threshold=2,
        validator_power=10,
    )
    with IntegrationNetwork.formed(
        binary=cometbft_binary,
        root=tmp_path,
        validators=1,
        non_validators=3,
        validator_governance=governance,
    ) as network:
        joining_keys = tuple(_validator_public_key(node.home) for node in network.nodes[1:])
        expected_keys = {_validator_public_key(node.home) for node in network.nodes}
        network.start_all(create_empty_blocks=True)

        height = network.nodes[0].rpc.broadcast_commit(
            _signed_additions(
                chain_id=network.chain_id,
                validator_public_keys=joining_keys,
                governance_keys=governance_keys[:2],
            )
        )
        _wait_for_validator_set(network, expected_keys)

        network.nodes[0].stop_cometbft()
        assert (
            network.nodes[1].rpc.broadcast_sync(
                signed_transaction(network.chain_id, "Quorum after governed validator admission")
            )
            == 0
        )
        snapshots = tuple(
            node.wait_for_snapshot(minimum_entries=1, timeout_seconds=30)
            for node in network.nodes[1:]
        )

        assert min(snapshot.height for snapshot in snapshots) > height
        assert set(network.nodes[1].rpc.validator_voting_powers().values()) == {10}


def _signed_additions(
    *,
    chain_id: str,
    validator_public_keys: tuple[bytes, ...],
    governance_keys: tuple[Ed25519PrivateKey, ...],
) -> bytes:
    change = ValidatorSetChange(
        chain_id=chain_id,
        sequence=1,
        changes=tuple(
            ValidatorMembershipChange(
                public_key=public_key,
                operation=ValidatorMembershipOperation.ADD,
            )
            for public_key in sorted(validator_public_keys)
        ),
    )
    transaction = SignedValidatorSetChange(
        change=change,
        approvals=tuple(
            sorted(
                (approve_validator_set_change(change, key) for key in governance_keys),
                key=lambda approval: approval.signer_public_key,
            )
        ),
    )
    return encode_validator_set_change(transaction)


def _validator_public_key(home: Path) -> bytes:
    descriptor = CometBFTValidatorProvisioner().genesis_validator(
        ValidatorIdentity(directory=home),
        name="validator",
        voting_power=10,
    )
    return descriptor.public_key


def _public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _wait_for_validator_set(network: IntegrationNetwork, expected_keys: set[bytes]) -> None:
    deadline = time.monotonic() + _VALIDATOR_SET_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        powers = network.nodes[0].rpc.validator_voting_powers()
        if set(powers) == expected_keys and set(powers.values()) == {10}:
            return
        time.sleep(0.05)
    raise AssertionError("governed validator set did not become active")
