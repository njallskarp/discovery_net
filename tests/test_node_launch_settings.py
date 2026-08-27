# Verifies that one launch value contains explicit, noncontradictory runtime settings.

from pathlib import Path

import pytest

from discovery_net.node.runtime import Endpoint, NodeLaunchSettings, PeerAddress
from tests.runtime_test_support import launch_settings

NODE_ID = "0123456789abcdef0123456789abcdef01234567"


def test_rpc_listener_may_explicitly_bind_a_deployment_managed_wildcard(tmp_path: Path) -> None:
    settings = launch_settings(tmp_path)

    configured = NodeLaunchSettings(
        home=settings.home,
        moniker=settings.moniker,
        genesis_path=settings.genesis_path,
        genesis_trust_anchor=settings.genesis_trust_anchor,
        abci_endpoint=settings.abci_endpoint,
        rpc_listen_endpoint=Endpoint(host="0.0.0.0", port=26657),
        p2p_listen_endpoint=settings.p2p_listen_endpoint,
    )

    assert configured.rpc_listen_endpoint.is_unspecified


def test_advertised_endpoint_must_be_dialable(tmp_path: Path) -> None:
    settings = launch_settings(tmp_path)

    with pytest.raises(ValueError, match="dialable"):
        NodeLaunchSettings(
            home=settings.home,
            moniker=settings.moniker,
            genesis_path=settings.genesis_path,
            genesis_trust_anchor=settings.genesis_trust_anchor,
            abci_endpoint=settings.abci_endpoint,
            rpc_listen_endpoint=settings.rpc_listen_endpoint,
            p2p_listen_endpoint=settings.p2p_listen_endpoint,
            p2p_advertised_endpoint=Endpoint(host="0.0.0.0", port=26656),
        )


def test_persistent_peers_must_have_distinct_node_identities(tmp_path: Path) -> None:
    settings = launch_settings(tmp_path)
    first = PeerAddress.parse(f"{NODE_ID}@127.0.0.1:26656")
    second = PeerAddress.parse(f"{NODE_ID}@127.0.0.1:36656")

    with pytest.raises(ValueError, match="duplicate node identities"):
        NodeLaunchSettings(
            home=settings.home,
            moniker=settings.moniker,
            genesis_path=settings.genesis_path,
            genesis_trust_anchor=settings.genesis_trust_anchor,
            abci_endpoint=settings.abci_endpoint,
            rpc_listen_endpoint=settings.rpc_listen_endpoint,
            p2p_listen_endpoint=settings.p2p_listen_endpoint,
            persistent_peers=(first, second),
        )
