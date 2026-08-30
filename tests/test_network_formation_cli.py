# Verifies the CLI exposes the complete independent-validator formation workflow.

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net.node.runtime._cometbft_process import _CometBFTProcess
from discovery_net.node.runtime.formation_process import main
from tests.runtime_test_support import write_generated_home, write_validator_identity


def _initialize_valid_home(_process: _CometBFTProcess, *, home: Path) -> None:
    write_generated_home(home)
    (home / "config" / "priv_validator_key.json").unlink()
    (home / "data" / "priv_validator_state.json").unlink()
    write_validator_identity(home, seed_byte=23)
    (home / "config" / "genesis.json").write_text(
        json.dumps(
            {
                "chain_id": "placeholder",
                "consensus_params": {
                    "block": {"max_bytes": "1000", "max_gas": "-1"},
                    "validator": {"pub_key_types": ["ed25519"]},
                },
            }
        )
    )


def test_cli_initializes_exports_forms_and_installs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "validator"
    descriptor = tmp_path / "validator.json"
    genesis = tmp_path / "genesis.json"
    governance_member = tmp_path / "governance-member.pem"
    governance_member.write_bytes(
        Ed25519PrivateKey.from_private_bytes(bytes([31]) * 32)
        .public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )

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
        assert main(("initialize-validator", "--home", str(home))) == 0
        assert (
            main(
                (
                    "export-validator",
                    "--home",
                    str(home),
                    "--output",
                    str(descriptor),
                    "--name",
                    "validator-a",
                )
            )
            == 0
        )
        assert (
            main(
                (
                    "create-genesis",
                    "--output",
                    str(genesis),
                    "--chain-id",
                    "discovery-1",
                    "--genesis-time",
                    "2026-08-27T12:00:00Z",
                    "--validator",
                    str(descriptor),
                    "--governance-member",
                    str(governance_member),
                    "--governance-threshold",
                    "1",
                )
            )
            == 0
        )

    digest = hashlib.sha256(genesis.read_bytes()).hexdigest()
    assert (
        main(
            (
                "install-genesis",
                "--home",
                str(home),
                "--genesis",
                str(genesis),
                "--chain-id",
                "discovery-1",
                "--genesis-sha256",
                digest,
            )
        )
        == 0
    )

    outputs = tuple(json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert len(outputs) == 4
    assert outputs[1]["descriptor"] == str(descriptor)
    assert outputs[2]["genesis_sha256"] == digest
    assert (home / "config" / "genesis.json").read_bytes() == genesis.read_bytes()
    document = json.loads(genesis.read_bytes())
    assert document["app_state"]["validator_governance"]["approval_threshold"] == 1
