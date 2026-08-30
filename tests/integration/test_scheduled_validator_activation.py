# Proves a scheduled activation extends the live validator set without resetting history.

import hashlib
from pathlib import Path

from discovery_net.node import ScheduledValidatorActivation, ValidatorPowerUpdate
from discovery_net.node.runtime import CometBFTValidatorProvisioner, ValidatorIdentity
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import signed_transaction

_VALIDATOR_POWER = 10


def test_scheduled_activation_preserves_history_and_transfers_quorum(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: A-only history → fixed-height activation → A outage; guards chain continuity."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=1,
        non_validators=3,
    ) as network:
        validator_public_keys = tuple(_validator_public_key(node.home) for node in network.nodes)
        network.start_all()
        history_heights = tuple(
            network.nodes[0].rpc.broadcast_commit(
                signed_transaction(network.chain_id, f"Existing contribution {index}")
            )
            for index in range(1, 3)
        )
        network.wait_for_convergence(minimum_entries=2)
        network.stop_all_cometbft()
        for node in network.nodes:
            node.stop_application()

        activation_height = history_heights[-1] + 2
        activation = ScheduledValidatorActivation(
            chain_id=network.chain_id,
            activation_height=activation_height,
            validators=tuple(
                sorted(
                    (
                        ValidatorPowerUpdate(
                            public_key=public_key,
                            voting_power=_VALIDATOR_POWER,
                        )
                        for public_key in validator_public_keys
                    ),
                    key=lambda validator: validator.public_key,
                )
            ),
        )
        activation_path = tmp_path / "validator-activation.json"
        activation_content = activation.encode()
        activation_path.write_bytes(activation_content)
        activation_sha256 = hashlib.sha256(activation_content).hexdigest()

        for node in network.nodes:
            node.start_application(
                validator_activation_path=activation_path,
                validator_activation_sha256=activation_sha256,
            )
        network.start_all_cometbft()

        upgrade_heights = tuple(
            network.nodes[0].rpc.broadcast_commit(
                signed_transaction(network.chain_id, f"Validator activation block {index}")
            )
            for index in range(1, 5)
        )
        activated_height = network.nodes[1].rpc.broadcast_commit(
            signed_transaction(network.chain_id, "Activated validator quorum")
        )
        network.wait_for_convergence(minimum_entries=7)

        expected_powers = {
            validator.public_key: validator.voting_power for validator in activation.validators
        }
        assert network.nodes[1].rpc.validator_voting_powers() == expected_powers
        assert upgrade_heights[0] > history_heights[-1]
        assert activation_height in upgrade_heights
        assert activated_height >= activation_height + 2

        network.nodes[0].stop_cometbft()
        continued_height = network.nodes[1].rpc.broadcast_commit(
            signed_transaction(network.chain_id, "Quorum after A stopped")
        )
        for node in network.nodes[1:]:
            node.wait_for_snapshot(minimum_height=continued_height, minimum_entries=8)

        assert continued_height > activated_height


def _validator_public_key(home: Path) -> bytes:
    return (
        CometBFTValidatorProvisioner()
        .genesis_validator(
            ValidatorIdentity(directory=home),
            name=home.name,
            voting_power=_VALIDATOR_POWER,
        )
        .public_key
    )
