# Verifies unambiguous TCP endpoint and authenticated peer parsing.

import pytest

from discovery_net.node.runtime import Endpoint, PeerAddress

NODE_ID = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize(
    ("text", "host", "rendered"),
    (
        ("127.0.0.1:26656", "127.0.0.1", "127.0.0.1:26656"),
        ("node.example:26656", "node.example", "node.example:26656"),
        ("[2001:db8::1]:26656", "2001:db8::1", "[2001:db8::1]:26656"),
    ),
)
def test_endpoint_round_trips_supported_authorities(text: str, host: str, rendered: str) -> None:
    endpoint = Endpoint.parse(text)

    assert endpoint.host == host
    assert str(endpoint) == rendered
    assert endpoint.tcp_url() == f"tcp://{rendered}"


@pytest.mark.parametrize(
    "text",
    ("", "localhost", "localhost:", "localhost:0", "localhost:65536", "user@host:1"),
)
def test_endpoint_rejects_incomplete_or_ambiguous_values(text: str) -> None:
    with pytest.raises(ValueError):
        Endpoint.parse(text)


def test_peer_address_normalizes_the_node_identity() -> None:
    peer = PeerAddress.parse(f"{NODE_ID.upper()}@127.0.0.1:26656")

    assert peer.node_id == NODE_ID
    assert str(peer) == f"{NODE_ID}@127.0.0.1:26656"


def test_peer_address_rejects_an_unspecified_dial_target() -> None:
    with pytest.raises(ValueError, match="dialable"):
        PeerAddress.parse(f"{NODE_ID}@0.0.0.0:26656")
