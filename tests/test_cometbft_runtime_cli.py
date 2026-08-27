# Verifies operator input is translated into typed CometBFT peer addresses.

import pytest

from discovery_net.node.runtime.process import _peer_addresses


def test_empty_persistent_peer_list_is_allowed() -> None:
    assert _peer_addresses("") == ()


def test_comma_separated_persistent_peers_are_parsed() -> None:
    first = "a" * 40 + "@node-a:26656"
    second = "b" * 40 + "@node-b:26656"

    assert tuple(str(peer) for peer in _peer_addresses(f"{first},{second}")) == (
        first,
        second,
    )


def test_malformed_persistent_peer_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="peer address"):
        _peer_addresses("not-a-peer")
