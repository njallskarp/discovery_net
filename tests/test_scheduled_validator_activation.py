# Verifies canonical, trust-anchored validator activations and their invariants.

import hashlib
from pathlib import Path

import pytest

from discovery_net.node import ScheduledValidatorActivation, ValidatorPowerUpdate

CHAIN_ID = "discovery-validator-activation-test"
VALIDATORS = tuple(
    ValidatorPowerUpdate(public_key=bytes([value]) * 32, voting_power=10) for value in (1, 2, 3, 4)
)


def activation() -> ScheduledValidatorActivation:
    return ScheduledValidatorActivation(
        chain_id=CHAIN_ID,
        activation_height=100,
        validators=VALIDATORS,
    )


def test_activation_round_trips_through_its_exact_trust_anchor(tmp_path: Path) -> None:
    expected = activation()
    path = tmp_path / "validator-activation.json"
    content = expected.encode()
    path.write_bytes(content)

    loaded = ScheduledValidatorActivation.from_trusted_file(
        path=path,
        expected_sha256=hashlib.sha256(content).hexdigest().upper(),
        expected_chain_id=CHAIN_ID,
    )

    assert loaded == expected
    assert loaded.updates_at(99) == ()
    assert loaded.updates_at(100) == VALIDATORS
    assert loaded.updates_at(101) == ()


def test_activation_rejects_untrusted_or_noncanonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "validator-activation.json"
    content = activation().encode()
    path.write_bytes(content)

    with pytest.raises(ValueError, match="SHA-256"):
        ScheduledValidatorActivation.from_trusted_file(
            path=path,
            expected_sha256="00" * 32,
            expected_chain_id=CHAIN_ID,
        )

    noncanonical = content + b"\n"
    path.write_bytes(noncanonical)
    with pytest.raises(ValueError, match="canonical"):
        ScheduledValidatorActivation.from_trusted_file(
            path=path,
            expected_sha256=hashlib.sha256(noncanonical).hexdigest(),
            expected_chain_id=CHAIN_ID,
        )


def test_activation_is_bound_to_one_chain(tmp_path: Path) -> None:
    path = tmp_path / "validator-activation.json"
    content = activation().encode()
    path.write_bytes(content)

    with pytest.raises(ValueError, match="different chain"):
        ScheduledValidatorActivation.from_trusted_file(
            path=path,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_chain_id="another-chain",
        )


@pytest.mark.parametrize(
    ("validators", "error"),
    [
        ((), "must not be empty"),
        ((VALIDATORS[1], VALIDATORS[0]), "ordered"),
        ((VALIDATORS[0], VALIDATORS[0]), "duplicate"),
        (
            (
                VALIDATORS[0],
                ValidatorPowerUpdate(public_key=VALIDATORS[1].public_key, voting_power=20),
            ),
            "equal voting power",
        ),
    ],
)
def test_activation_rejects_an_ambiguous_validator_set(
    validators: tuple[ValidatorPowerUpdate, ...],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        ScheduledValidatorActivation(
            chain_id=CHAIN_ID,
            activation_height=100,
            validators=validators,
        )
