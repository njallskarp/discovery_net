"""Load the fixed validator electorate from the same pinned genesis as CometBFT."""

import base64
from pathlib import Path

from discovery_net.node.runtime._cometbft_limits import MAX_TOTAL_VOTING_POWER
from discovery_net.node.runtime.genesis import GenesisTrustAnchor, _VerifiedGenesis


def load_voting_power(
    *, chain_id: str, genesis: Path | None, genesis_sha256: str | None
) -> dict[bytes, int]:
    """Without a pinned genesis, revocation authority is empty (fail closed).

    This protocol emits no validator updates, so genesis is the active electorate
    at every height. Membership updates must change this state source before use.
    """
    if genesis is None and genesis_sha256 is None:
        return {}
    if genesis is None or genesis_sha256 is None:
        raise ValueError("genesis and genesis_sha256 must be supplied together")
    verified = _VerifiedGenesis.from_path(
        path=genesis,
        trust_anchor=GenesisTrustAnchor(expected_chain_id=chain_id, expected_sha256=genesis_sha256),
    )
    validators = verified.document.validators
    if not isinstance(validators, list):
        raise ValueError("genesis validators must be a list")
    powers: dict[bytes, int] = {}
    for validator in validators:
        if not isinstance(validator, dict):
            raise ValueError("invalid genesis validator")
        public_key = validator.get("pub_key")
        if not isinstance(public_key, dict) or public_key.get("type") != "tendermint/PubKeyEd25519":
            raise ValueError("validator must have an Ed25519 public key")
        encoded = public_key.get("value")
        if not isinstance(encoded, str):
            raise ValueError("validator public key must be base64 text")
        key = base64.b64decode(encoded, validate=True)
        if len(key) != 32 or key in powers:
            raise ValueError("validator public keys must be unique 32-byte keys")
        power = validator.get("power")
        if isinstance(power, str) and power.isascii() and power.isdecimal():
            power = int(power)
        if (
            not isinstance(power, int)
            or isinstance(power, bool)
            or not 0 < power <= MAX_TOTAL_VOTING_POWER
        ):
            raise ValueError("genesis validator power must be a positive bounded integer")
        powers[key] = power
    if not powers or sum(powers.values()) > MAX_TOTAL_VOTING_POWER:
        raise ValueError("genesis must contain a nonempty, bounded validator electorate")
    return powers
