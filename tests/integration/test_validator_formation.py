# Verifies independently formed validators reach consensus and preserve signing state.

import hashlib
import json
from pathlib import Path

from discovery_net.node.runtime import (
    CometBFTValidatorProvisioner,
    GenesisTrustAnchor,
    ValidatorIdentity,
)
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import signed_transaction


def test_formed_validator_network_commits_survives_outage_and_restarts(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: independent identities → shared genesis → quorum → restart; guards key state."""
    with IntegrationNetwork.formed(
        binary=cometbft_binary,
        root=tmp_path,
        validators=4,
    ) as network:
        network.start_all()
        first_height = network.validators[0].rpc.broadcast_commit(
            signed_transaction(network.chain_id, "Formed network")
        )
        network.wait_for_convergence(minimum_entries=1)

        stopped = network.validators[-1]
        state_path = stopped.home / "data" / "priv_validator_state.json"
        state_before_outage = _signed_height(state_path)
        stopped.stop_cometbft()

        second_height = network.validators[0].rpc.broadcast_commit(
            signed_transaction(network.chain_id, "Quorum without one validator")
        )
        for validator in network.validators[:-1]:
            validator.wait_for_snapshot(minimum_height=second_height, minimum_entries=2)

        stopped.start_cometbft(peers=(network.validators[0].peer_address,))
        network.wait_for_convergence(minimum_entries=2)
        third_height = stopped.rpc.broadcast_commit(
            signed_transaction(network.chain_id, "Restarted validator")
        )
        network.wait_for_convergence(minimum_entries=3)

        assert first_height > 0
        assert second_height > first_height
        assert third_height > second_height
        assert _signed_height(state_path) > state_before_outage

        key_before = (stopped.home / "config" / "priv_validator_key.json").read_bytes()
        state_before = state_path.read_bytes()
        provisioner = CometBFTValidatorProvisioner(binary=cometbft_binary)
        genesis_path = tmp_path / "genesis.json"
        identity = ValidatorIdentity(directory=stopped.home)
        try:
            provisioner.install_genesis(
                identity=identity,
                genesis_path=genesis_path,
                genesis_trust_anchor=_genesis_trust_anchor(genesis_path, network.chain_id),
            )
        except ValueError as error:
            assert "runtime state" in str(error) or "pristine identity" in str(error)
        else:
            raise AssertionError("an active validator home was rebound to genesis")
        assert (stopped.home / "config" / "priv_validator_key.json").read_bytes() == key_before
        assert state_path.read_bytes() == state_before


def _genesis_trust_anchor(path: Path, chain_id: str) -> GenesisTrustAnchor:
    """Return the exact trust anchor used to test post-start reprovisioning rejection."""
    return GenesisTrustAnchor(
        expected_chain_id=chain_id,
        expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def _signed_height(path: Path) -> int:
    document: object = json.loads(path.read_bytes())
    if not isinstance(document, dict):
        raise AssertionError("private-validator state must be an object")
    height = document.get("height")
    if not isinstance(height, str) or not height.isdecimal():
        raise AssertionError("private-validator state must contain a decimal height")
    return int(height)
