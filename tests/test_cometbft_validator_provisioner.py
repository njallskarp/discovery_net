# Verifies validator generation and provisioning preserve the key/state safety boundary.

import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from discovery_net.node.runtime import (
    CometBFTValidatorProvisioner,
    GenesisTrustAnchor,
    ValidatorIdentity,
)
from discovery_net.node.runtime._cometbft_process import _CometBFTProcess
from tests.runtime_test_support import write_generated_home, write_validator_identity


def _initialize_valid_home(_process: _CometBFTProcess, *, home: Path) -> None:
    write_generated_home(home)
    (home / "config" / "priv_validator_key.json").unlink()
    (home / "data" / "priv_validator_state.json").unlink()
    write_validator_identity(home, seed_byte=19)


def _genesis(path: Path, *, public_key: bytes) -> GenesisTrustAnchor:
    content = json.dumps(
        {
            "chain_id": "discovery-1",
            "initial_height": "1",
            "validators": [
                {
                    "pub_key": {
                        "type": "tendermint/PubKeyEd25519",
                        "value": base64.b64encode(public_key).decode("ascii"),
                    }
                }
            ],
        }
    ).encode()
    path.write_bytes(content)
    return GenesisTrustAnchor(
        expected_chain_id="discovery-1",
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )


def test_initialize_describe_and_bind_one_pristine_identity(tmp_path: Path) -> None:
    provisioner = CometBFTValidatorProvisioner()
    home = tmp_path / "validator-home"

    with (
        patch.object(
            _CometBFTProcess,
            "require_compatible_command_surface",
            autospec=True,
        ),
        patch.object(
            _CometBFTProcess,
            "initialize",
            autospec=True,
            side_effect=_initialize_valid_home,
        ),
    ):
        identity = provisioner.initialize_home(home=home)

    descriptor = provisioner.genesis_validator(identity, name="validator-a", voting_power=10)
    key_content = identity.key_path.read_bytes()
    state_content = identity.state_path.read_bytes()
    genesis_path = tmp_path / "genesis.json"
    trust_anchor = _genesis(genesis_path, public_key=descriptor.public_key)

    provisioner.install_genesis(
        identity=identity,
        genesis_path=genesis_path,
        genesis_trust_anchor=trust_anchor,
    )

    assert (home / "config" / "priv_validator_key.json").read_bytes() == key_content
    assert (home / "data" / "priv_validator_state.json").read_bytes() == state_content
    assert (home / "config" / "genesis.json").read_bytes() == genesis_path.read_bytes()


def test_install_rejects_a_home_not_initialized_by_the_provisioner(tmp_path: Path) -> None:
    home = tmp_path / "foreign-home"
    _initialize_valid_home(_CometBFTProcess(binary=Path("cometbft")), home=home)
    identity = ValidatorIdentity(directory=home)
    public_key = CometBFTValidatorProvisioner().genesis_validator(
        identity,
        name="validator-a",
        voting_power=10,
    ).public_key
    genesis_path = tmp_path / "genesis.json"
    trust_anchor = _genesis(genesis_path, public_key=public_key)

    with pytest.raises(ValueError, match="not awaiting"):
        CometBFTValidatorProvisioner().install_genesis(
            identity=identity,
            genesis_path=genesis_path,
            genesis_trust_anchor=trust_anchor,
        )

    assert (home / "config" / "genesis.json").read_text() == "{}"


def test_non_pristine_signing_state_is_rejected_before_home_mutation(tmp_path: Path) -> None:
    home = tmp_path / "validator-home"
    _initialize_valid_home(_CometBFTProcess(binary=Path("cometbft")), home=home)
    identity = ValidatorIdentity(directory=home)
    public_key = CometBFTValidatorProvisioner().genesis_validator(
        identity,
        name="validator-a",
        voting_power=10,
    ).public_key
    (home / "data" / "priv_validator_state.json").write_text(
        json.dumps({"height": "4", "round": 0, "step": 3})
    )
    (home / "data" / "priv_validator_state.json").chmod(0o600)
    genesis_path = tmp_path / "genesis.json"
    trust_anchor = _genesis(genesis_path, public_key=public_key)

    with pytest.raises(ValueError, match="pristine identity"):
        CometBFTValidatorProvisioner().install_genesis(
            identity=identity,
            genesis_path=genesis_path,
            genesis_trust_anchor=trust_anchor,
        )

    assert (home / "config" / "genesis.json").read_text() == "{}"


def test_initialization_never_overwrites_an_existing_home(tmp_path: Path) -> None:
    home = tmp_path / "validator-home"
    home.mkdir()
    marker = home / "state"
    marker.write_text("preserve")

    with pytest.raises(FileExistsError):
        CometBFTValidatorProvisioner().initialize_home(home=home)

    assert marker.read_text() == "preserve"


def test_identity_outside_genesis_is_rejected_before_home_mutation(tmp_path: Path) -> None:
    home = tmp_path / "validator-home"
    _initialize_valid_home(_CometBFTProcess(binary=Path("cometbft")), home=home)
    genesis_path = tmp_path / "genesis.json"
    trust_anchor = _genesis(genesis_path, public_key=bytes(range(32)))

    with pytest.raises(ValueError, match="not a member"):
        CometBFTValidatorProvisioner().install_genesis(
            identity=ValidatorIdentity(directory=home),
            genesis_path=genesis_path,
            genesis_trust_anchor=trust_anchor,
        )

    assert (home / "config" / "genesis.json").read_text() == "{}"


def test_identity_rejects_a_private_key_that_does_not_match_its_public_key(
    tmp_path: Path,
) -> None:
    home = tmp_path / "validator-home"
    _initialize_valid_home(_CometBFTProcess(binary=Path("cometbft")), home=home)
    key_path = home / "config" / "priv_validator_key.json"
    document = json.loads(key_path.read_bytes())
    private_key = bytearray(base64.b64decode(document["priv_key"]["value"]))
    private_key[-1] ^= 1
    document["priv_key"]["value"] = base64.b64encode(private_key).decode("ascii")
    key_path.write_text(json.dumps(document))
    key_path.chmod(0o600)

    with pytest.raises(ValueError, match="does not match"):
        CometBFTValidatorProvisioner().genesis_validator(
            ValidatorIdentity(directory=home),
            name="validator-a",
            voting_power=10,
        )


def test_identity_rejects_private_files_visible_to_other_users(tmp_path: Path) -> None:
    home = tmp_path / "validator-home"
    _initialize_valid_home(_CometBFTProcess(binary=Path("cometbft")), home=home)
    (home / "config" / "priv_validator_key.json").chmod(0o644)

    with pytest.raises(ValueError, match="group or other users"):
        CometBFTValidatorProvisioner().genesis_validator(
            ValidatorIdentity(directory=home),
            name="validator-a",
            voting_power=10,
        )
