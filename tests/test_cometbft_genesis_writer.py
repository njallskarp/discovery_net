# Verifies shared genesis formation is deterministic, public-only, and non-overwriting.

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net.node.runtime import (
    CometBFTGenesisWriter,
    GenesisValidator,
    ValidatorGovernanceConfig,
)
from discovery_net.node.runtime._cometbft_process import _CometBFTProcess


def _initialize_template(_process: _CometBFTProcess, *, home: Path) -> None:
    config = home / "config"
    config.mkdir(parents=True)
    (config / "genesis.json").write_text(
        json.dumps(
            {
                "chain_id": "generated",
                "consensus_params": {
                    "block": {"max_bytes": "1000", "max_gas": "-1"},
                    "validator": {"pub_key_types": ["ed25519"]},
                },
            }
        )
    )


def test_writer_forms_deterministic_genesis_from_public_descriptors(tmp_path: Path) -> None:
    validators = (
        GenesisValidator(name="a", public_key=bytes(range(32)), voting_power=10),
        GenesisValidator(name="b", public_key=bytes(range(1, 33)), voting_power=20),
    )
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

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
            side_effect=_initialize_template,
        ),
    ):
        first_anchor = CometBFTGenesisWriter().write(
            path=first_path,
            chain_id="discovery-1",
            genesis_time=datetime(2026, 8, 27, 12, tzinfo=UTC),
            validators=validators,
        )
        second_anchor = CometBFTGenesisWriter().write(
            path=second_path,
            chain_id="discovery-1",
            genesis_time=datetime(2026, 8, 27, 12, tzinfo=UTC),
            validators=validators,
        )

    document = json.loads(first_path.read_bytes())
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_anchor == second_anchor
    assert document["initial_height"] == "1"
    assert document["app_hash"] == ""
    assert [validator["name"] for validator in document["validators"]] == ["a", "b"]
    assert "priv_key" not in first_path.read_text()


def test_writer_rejects_duplicates_before_invoking_cometbft(tmp_path: Path) -> None:
    validator = GenesisValidator(name="a", public_key=bytes(range(32)), voting_power=10)

    with (
        patch.object(_CometBFTProcess, "initialize", autospec=True) as initialize,
        pytest.raises(ValueError, match="duplicate public keys"),
    ):
        CometBFTGenesisWriter().write(
            path=tmp_path / "genesis.json",
            chain_id="discovery-1",
            genesis_time=datetime.now(UTC),
            validators=(validator, validator.model_copy(update={"name": "b"})),
        )

    initialize.assert_not_called()


def test_writer_places_threshold_governance_and_equal_validator_power_in_genesis(
    tmp_path: Path,
) -> None:
    validator = GenesisValidator(name="a", public_key=bytes(range(32)), voting_power=10)
    governance_keys = tuple(
        Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32)
        .public_key()
        .public_bytes(Encoding.Raw, PublicFormat.Raw)
        for value in (1, 2, 3)
    )
    path = tmp_path / "genesis.json"

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
            side_effect=_initialize_template,
        ),
    ):
        CometBFTGenesisWriter().write(
            path=path,
            chain_id="discovery-1",
            genesis_time=datetime(2026, 8, 27, 12, tzinfo=UTC),
            validators=(validator,),
            validator_governance=ValidatorGovernanceConfig(
                member_public_keys=tuple(sorted(governance_keys)),
                approval_threshold=2,
                validator_power=10,
            ),
        )

    document = json.loads(path.read_bytes())
    governance = document["app_state"]["validator_governance"]
    assert governance["approval_threshold"] == 2
    assert governance["validator_power"] == 10
    assert governance["sequence"] == 0
    assert governance["validator_public_keys"] == [validator.public_key.hex()]


def test_writer_rejects_total_voting_power_overflow_before_invoking_cometbft(
    tmp_path: Path,
) -> None:
    maximum = ((1 << 63) - 1) // 8
    validators = (
        GenesisValidator(name="a", public_key=bytes(range(32)), voting_power=maximum),
        GenesisValidator(name="b", public_key=bytes(range(1, 33)), voting_power=1),
    )

    with (
        patch.object(_CometBFTProcess, "initialize", autospec=True) as initialize,
        pytest.raises(ValueError, match="total voting power"),
    ):
        CometBFTGenesisWriter().write(
            path=tmp_path / "genesis.json",
            chain_id="discovery-1",
            genesis_time=datetime.now(UTC),
            validators=validators,
        )

    initialize.assert_not_called()


def test_writer_never_overwrites_an_existing_genesis(tmp_path: Path) -> None:
    path = tmp_path / "genesis.json"
    path.write_bytes(b"existing")
    validator = GenesisValidator(name="a", public_key=bytes(range(32)), voting_power=10)

    with (
        patch.object(_CometBFTProcess, "initialize", autospec=True) as initialize,
        pytest.raises(FileExistsError),
    ):
        CometBFTGenesisWriter().write(
            path=path,
            chain_id="discovery-1",
            genesis_time=datetime.now(UTC),
            validators=(validator,),
        )

    initialize.assert_not_called()
    assert path.read_bytes() == b"existing"
