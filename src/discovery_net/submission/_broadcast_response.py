# Defines the private response returned by a CometBFT broadcast call.

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class _BroadcastResponse:
    """The immediate response returned by a CometBFT broadcast call."""

    transaction_hash: str
    check_tx_code: int
