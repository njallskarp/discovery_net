# Verifies typed peer addresses and safe CometBFT networking profiles.

import pytest

from discovery_net.node import (
    CometBFTP2PConfig,
    NetworkScope,
    NodeNetworkConfig,
    PeerAddress,
    PeerEndpoint,
)

NODE_ID = "a" * 40


def test_peer_address_round_trips_ipv4_hostname_and_ipv6_endpoints() -> None:
    for encoded in (
        f"{NODE_ID}@127.0.0.1:26656",
        f"{NODE_ID}@alice.discovery.test:26656",
        f"{NODE_ID}@[2001:db8::1]:26656",
    ):
        assert str(PeerAddress.parse(encoded)) == encoded


@pytest.mark.parametrize(
    "encoded",
    (
        "127.0.0.1:26656",
        "not-hex@127.0.0.1:26656",
        f"{NODE_ID}@127.0.0.1",
        f"{NODE_ID}@127.0.0.1:0",
        f"{NODE_ID}@127.0.0.1:65536",
        f"{NODE_ID}@bad host:26656",
    ),
)
def test_peer_address_rejects_noncanonical_values(encoded: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        PeerAddress.parse(encoded)


@pytest.mark.parametrize(
    ("scope", "endpoint", "strict", "duplicates"),
    (
        (NetworkScope.PUBLIC, "8.8.8.8:26656", True, False),
        (NetworkScope.PRIVATE, "172.20.0.2:26656", False, False),
        (NetworkScope.LOOPBACK, "127.0.0.1:26656", False, True),
    ),
)
def test_network_scope_derives_security_sensitive_cometbft_settings(
    scope: NetworkScope,
    endpoint: str,
    strict: bool,
    duplicates: bool,
) -> None:
    config = CometBFTP2PConfig.from_node_config(
        NodeNetworkConfig(
            scope=scope,
            advertised_endpoint=PeerEndpoint.parse(endpoint),
            persistent_peers=(PeerAddress.parse(f"{NODE_ID}@peer.example:26656"),),
        )
    )

    assert config.addr_book_strict is strict
    assert config.allow_duplicate_ip is duplicates
    assert config.peer_exchange is True
    assert config.persistent_peers == f"{NODE_ID}@peer.example:26656"


@pytest.mark.parametrize(
    ("scope", "endpoint"),
    (
        (NetworkScope.PUBLIC, "127.0.0.1:26656"),
        (NetworkScope.PUBLIC, "10.0.0.1:26656"),
        (NetworkScope.PRIVATE, "8.8.8.8:26656"),
        (NetworkScope.LOOPBACK, "172.20.0.2:26656"),
        (NetworkScope.LOOPBACK, "peer.example:26656"),
    ),
)
def test_network_scope_rejects_conflicting_literal_addresses(
    scope: NetworkScope,
    endpoint: str,
) -> None:
    with pytest.raises(ValueError, match="advertise"):
        NodeNetworkConfig(
            scope=scope,
            advertised_endpoint=PeerEndpoint.parse(endpoint),
        )


def test_cometbft_arguments_keep_peer_exchange_enabled_without_unsafe_rpc() -> None:
    config = CometBFTP2PConfig.from_node_config(
        NodeNetworkConfig(
            scope=NetworkScope.PRIVATE,
            advertised_endpoint=PeerEndpoint.parse("node-a:26656"),
        )
    )

    assert config.command_arguments() == (
        "--p2p.external-address",
        "node-a:26656",
        "--p2p.persistent_peers",
        "",
        "--p2p.pex=true",
    )
