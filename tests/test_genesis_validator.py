# Verifies public validator descriptors are strict, portable, and secret-free.

import base64

import pytest
from pydantic import ValidationError

from discovery_net.node.runtime import GenesisValidator


def test_descriptor_round_trips_through_json() -> None:
    public_key = bytes(range(32))
    validator = GenesisValidator(
        name="validator-a",
        public_key=public_key,
        voting_power=10,
    )

    decoded = GenesisValidator.model_validate_json(validator.model_dump_json())

    assert decoded == validator
    assert decoded.public_key == public_key
    assert base64.b64encode(public_key).decode("ascii") in validator.model_dump_json()
    assert validator.address == "630DCD2966C4336691125448BBB25B4FF412A49C"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("name", " "),
        ("public_key", b"short"),
        ("voting_power", 0),
        ("voting_power", True),
        ("voting_power", "10"),
        ("voting_power", 1 << 63),
    ),
)
def test_descriptor_rejects_values_cometbft_cannot_use(field: str, value: object) -> None:
    values: dict[str, object] = {
        "name": "validator-a",
        "public_key": bytes(range(32)),
        "voting_power": 10,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        GenesisValidator.model_validate(values)
