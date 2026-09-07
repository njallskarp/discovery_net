"""Deterministic permission checks against the chain's validator voting power."""

from collections.abc import Mapping


def can_revoke(*, signer_public_key: bytes, voting_power: Mapping[bytes, int]) -> bool:
    """Only an authenticated signer with positive validator voting power may revoke."""
    return voting_power.get(signer_public_key, 0) > 0
