# Verifies that node policy becomes one explicit and shell-free CometBFT command.

from pathlib import Path

from discovery_net.node import (
    CometBFTStartCommand,
    NetworkScope,
    NodeNetworkConfig,
    PeerAddress,
    PeerEndpoint,
)


def test_start_command_contains_safe_loopback_discovery_settings() -> None:
    peer = PeerAddress.parse(f"{'a' * 40}@127.0.0.1:27656")

    command = CometBFTStartCommand(
        home=Path("/var/lib/cometbft"),
        moniker="alice",
        proxy_app="app:26658",
        rpc_listen_address="0.0.0.0:26657",
        p2p_listen_address="0.0.0.0:26656",
        network=NodeNetworkConfig(
            scope=NetworkScope.LOOPBACK,
            advertised_endpoint=PeerEndpoint.parse("127.0.0.1:26656"),
            persistent_peers=(peer,),
        ),
    ).arguments()

    assert command[:4] == ("cometbft", "start", "--home", "/var/lib/cometbft")
    assert "--p2p.pex=true" in command
    assert str(peer) in command
    assert not any("unsafe" in argument for argument in command)
