# Verifies typed launch settings become a parsed, restrictive CometBFT configuration.

import stat
import tomllib
from pathlib import Path

from discovery_net.node.runtime import Endpoint, NodeLaunchSettings, PeerAddress
from discovery_net.node.runtime._cometbft_config import _CometBFTConfig
from tests.runtime_test_support import launch_settings, write_generated_home

NODE_ID = "0123456789abcdef0123456789abcdef01234567"


def test_config_applies_and_reparses_every_owned_setting(tmp_path: Path) -> None:
    settings = launch_settings(tmp_path)
    write_generated_home(settings.home)
    path = settings.home / "config" / "config.toml"
    path.chmod(0o640)
    peer = PeerAddress.parse(f"{NODE_ID}@127.0.0.1:36656")
    configured = NodeLaunchSettings(
        home=settings.home,
        moniker="joining-node",
        genesis_path=settings.genesis_path,
        genesis_trust_anchor=settings.genesis_trust_anchor,
        abci_endpoint=settings.abci_endpoint,
        rpc_listen_endpoint=Endpoint(host="127.0.0.1", port=36657),
        p2p_listen_endpoint=Endpoint(host="0.0.0.0", port=36656),
        p2p_advertised_endpoint=Endpoint(host="node.example", port=36656),
        persistent_peers=(peer,),
        peer_exchange=False,
        peer_admission=settings.peer_admission,
        create_empty_blocks=False,
        log_level="error",
    )

    _CometBFTConfig().apply_and_verify(path=path, settings=configured)

    document = tomllib.loads(path.read_text())
    assert document["moniker"] == "joining-node"
    assert document["proxy_app"] == "127.0.0.1:26658"
    assert document["abci"] == "grpc"
    assert document["rpc"]["laddr"] == "tcp://127.0.0.1:36657"
    assert document["rpc"]["unsafe"] is False
    assert document["p2p"]["laddr"] == "tcp://0.0.0.0:36656"
    assert document["p2p"]["external_address"] == "node.example:36656"
    assert document["p2p"]["persistent_peers"] == str(peer)
    assert document["p2p"]["allow_duplicate_ip"] is True
    assert document["consensus"]["create_empty_blocks"] is False
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert not tuple(path.parent.glob(f".{path.name}.*"))
