# Re-exports the CometBFT limits used by network-formation internals.

from discovery_net.cometbft_limits import (
    MAX_CHAIN_ID_CHARACTERS,
    MAX_TOTAL_VOTING_POWER,
    MAX_VALIDATORS,
)

__all__ = ["MAX_CHAIN_ID_CHARACTERS", "MAX_TOTAL_VOTING_POWER", "MAX_VALIDATORS"]
