# Provides concise trusted-genesis and launch settings shared by runtime tests.

import hashlib
from pathlib import Path

from discovery_net.node.runtime import (
    Endpoint,
    GenesisTrustAnchor,
    NodeLaunchSettings,
    PeerAdmissionPolicy,
)

CHAIN_ID = "discovery-test-chain"
GENESIS_CONTENT = b'{"chain_id":"discovery-test-chain","initial_height":"0"}'


def write_genesis(path: Path, content: bytes = GENESIS_CONTENT) -> GenesisTrustAnchor:
    """Write genesis test input and return the matching trust anchor."""
    path.write_bytes(content)
    return GenesisTrustAnchor(
        expected_chain_id=CHAIN_ID,
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )


def launch_settings(root: Path) -> NodeLaunchSettings:
    """Return one complete loopback launch configuration rooted in a test directory."""
    genesis_path = root / "source-genesis.json"
    return NodeLaunchSettings(
        home=root / "cometbft",
        moniker="test-node",
        genesis_path=genesis_path,
        genesis_trust_anchor=write_genesis(genesis_path),
        abci_endpoint=Endpoint(host="127.0.0.1", port=26658),
        rpc_listen_endpoint=Endpoint(host="127.0.0.1", port=26657),
        p2p_listen_endpoint=Endpoint(host="127.0.0.1", port=26656),
        peer_exchange=False,
        peer_admission=PeerAdmissionPolicy(
            address_book_strict=False,
            allow_duplicate_ip=True,
        ),
        create_empty_blocks=False,
        log_level="error",
    )


def write_generated_home(home: Path) -> None:
    """Create the minimal file layout emitted by CometBFT init for isolated tests."""
    config = home / "config"
    data = home / "data"
    config.mkdir(parents=True)
    data.mkdir()
    (config / "config.toml").write_text(
        """moniker = "generated"
proxy_app = "tcp://127.0.0.1:26658"
abci = "socket"
log_level = "info"

[rpc]
laddr = "tcp://127.0.0.1:26657"
unsafe = false
cors_allowed_origins = []
grpc_laddr = ""
pprof_laddr = ""

[p2p]
laddr = "tcp://0.0.0.0:26656"
external_address = ""
persistent_peers = ""
pex = true
addr_book_strict = true
allow_duplicate_ip = false

[consensus]
create_empty_blocks = true
"""
    )
    (config / "genesis.json").write_text("{}")
    (config / "node_key.json").write_text('{"id":"node"}')
    (config / "priv_validator_key.json").write_text(
        '{"pub_key":{"type":"tendermint/PubKeyEd25519","value":"generated"}}'
    )
    (data / "priv_validator_state.json").write_text('{"height":"0"}')
