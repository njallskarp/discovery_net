# Proves asynchronous admission changes a live CometBFT quorum without resetting history.

import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net.node.runtime import CometBFTValidatorProvisioner, ValidatorIdentity
from discovery_net.wire import (
    ValidatorMembershipOperation,
    approve_validator_proposal,
    complete_validator_nomination,
    encode_validator_governance_transaction,
    propose_validator_membership,
    validator_proposal_id,
)
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import signed_transaction

_VALIDATOR_SET_TIMEOUT_SECONDS = 30


def test_admitted_validator_signs_after_one_genesis_validator_leaves(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    governance_keys = tuple(
        Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32) for value in (31, 32, 33, 34)
    )
    with IntegrationNetwork.formed(
        binary=cometbft_binary,
        root=tmp_path,
        validators=4,
        non_validators=1,
        governance_private_keys=governance_keys,
    ) as network:
        provisioner = CometBFTValidatorProvisioner(binary=cometbft_binary)
        candidate_governance_key = Ed25519PrivateKey.from_private_bytes(bytes([35]) * 32)
        candidate_consensus_nomination = provisioner.nominate_validator(
            ValidatorIdentity(directory=network.nodes[4].home),
            chain_id=network.chain_id,
            governance_public_key=candidate_governance_key.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw
            ),
        )
        candidate = complete_validator_nomination(
            nomination=candidate_consensus_nomination,
            governance_private_key=candidate_governance_key,
        )
        proposal = propose_validator_membership(
            chain_id=network.chain_id,
            operation=ValidatorMembershipOperation.ADD,
            operator=candidate.operator,
            sponsor_private_key=governance_keys[0],
            nomination=candidate,
        )
        proposal_id = validator_proposal_id(proposal)
        expected_keys = {
            *(_validator_public_key(node.home) for node in network.validators),
            candidate.operator.consensus_public_key,
        }
        network.start_all(create_empty_blocks=True)

        proposal_height = network.nodes[0].rpc.broadcast_commit(
            encode_validator_governance_transaction(proposal)
        )
        assert candidate.operator.consensus_public_key not in (
            network.nodes[0].rpc.validator_voting_powers()
        )

        first_approval = approve_validator_proposal(
            chain_id=network.chain_id,
            proposal_id=proposal_id,
            private_key=governance_keys[1],
        )
        first_approval_height = network.nodes[1].rpc.broadcast_commit(
            encode_validator_governance_transaction(first_approval)
        )
        assert first_approval_height > proposal_height
        assert candidate.operator.consensus_public_key not in (
            network.nodes[0].rpc.validator_voting_powers()
        )

        threshold_approval = approve_validator_proposal(
            chain_id=network.chain_id,
            proposal_id=proposal_id,
            private_key=governance_keys[2],
        )
        threshold_height = network.nodes[2].rpc.broadcast_commit(
            encode_validator_governance_transaction(threshold_approval)
        )
        assert threshold_height > first_approval_height
        _wait_for_validator_set(network, expected_keys)

        network.nodes[0].stop_cometbft()
        assert (
            network.nodes[4].rpc.broadcast_sync(
                signed_transaction(
                    network.chain_id,
                    "The admitted validator preserves quorum",
                )
            )
            == 0
        )
        snapshots = tuple(
            node.wait_for_snapshot(minimum_entries=1, timeout_seconds=30)
            for node in network.nodes[1:]
        )

        assert min(snapshot.height for snapshot in snapshots) > threshold_height
        assert set(network.nodes[4].rpc.validator_voting_powers().values()) == {10}


def _validator_public_key(home: Path) -> bytes:
    descriptor = CometBFTValidatorProvisioner().genesis_validator(
        ValidatorIdentity(directory=home),
        name="validator",
        voting_power=10,
    )
    return descriptor.public_key


def _wait_for_validator_set(network: IntegrationNetwork, expected_keys: set[bytes]) -> None:
    deadline = time.monotonic() + _VALIDATOR_SET_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        powers = network.nodes[0].rpc.validator_voting_powers()
        if set(powers) == expected_keys and set(powers.values()) == {10}:
            return
        time.sleep(0.05)
    raise AssertionError("governed validator set did not become active")
