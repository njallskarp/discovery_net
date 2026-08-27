# Verifies fresh and repeated node-home preparation with the real CometBFT binary.

import hashlib
import json
import subprocess
from pathlib import Path

from discovery_net.node.runtime import (
    Endpoint,
    GenesisTrustAnchor,
    NodeLaunchSettings,
    PeerAdmissionPolicy,
)
from discovery_net.node.runtime._cometbft_config import _CometBFTConfig
from discovery_net.node.runtime._cometbft_home import _CometBFTHome
from discovery_net.node.runtime._cometbft_process import _CometBFTProcess
from discovery_net.node.runtime.genesis import _VerifiedGenesis


def test_real_cometbft_initialization_installs_trusted_genesis_and_preserves_identity(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    source_home = tmp_path / "network-source"
    _run((str(cometbft_binary), "init", "--home", str(source_home)))
    genesis_path = source_home / "config" / "genesis.json"
    genesis_content = genesis_path.read_bytes()
    document: object = json.loads(genesis_content)
    if not isinstance(document, dict) or not isinstance(document.get("chain_id"), str):
        raise AssertionError("CometBFT generated a genesis without a chain ID")
    trust_anchor = GenesisTrustAnchor(
        expected_chain_id=document["chain_id"],
        expected_sha256=hashlib.sha256(genesis_content).hexdigest(),
    )
    settings = NodeLaunchSettings(
        home=tmp_path / "joining-node",
        moniker="joining-node",
        genesis_path=genesis_path,
        genesis_trust_anchor=trust_anchor,
        abci_endpoint=Endpoint(host="127.0.0.1", port=26658),
        rpc_listen_endpoint=Endpoint(host="127.0.0.1", port=26657),
        p2p_listen_endpoint=Endpoint(host="127.0.0.1", port=26656),
        peer_exchange=False,
        peer_admission=PeerAdmissionPolicy(
            address_book_strict=False,
            allow_duplicate_ip=True,
        ),
    )
    process = _CometBFTProcess(binary=cometbft_binary)
    home = _CometBFTHome(
        path=settings.home,
        config=_CometBFTConfig(),
        process=process,
    )
    verified = _VerifiedGenesis.from_path(
        path=genesis_path,
        trust_anchor=trust_anchor,
    )

    process.require_compatible_command_surface()
    home.prepare(genesis=verified, settings=settings)
    first_node_id = _run(
        (str(cometbft_binary), "show-node-id", "--home", str(settings.home))
    ).strip()
    node_key = (settings.home / "config" / "node_key.json").read_bytes()
    validator_key = (settings.home / "config" / "priv_validator_key.json").read_bytes()
    joining_validator_public_key = _public_key_value(validator_key)
    genesis_validator_public_keys = {
        _public_key_value(json.dumps({"pub_key": validator["pub_key"]}).encode())
        for validator in document.get("validators", [])
    }

    home.prepare(genesis=verified, settings=settings)

    assert (settings.home / "config" / "genesis.json").read_bytes() == genesis_content
    assert (
        _run((str(cometbft_binary), "show-node-id", "--home", str(settings.home))).strip()
        == first_node_id
    )
    assert (settings.home / "config" / "node_key.json").read_bytes() == node_key
    assert (settings.home / "config" / "priv_validator_key.json").read_bytes() == validator_key
    assert joining_validator_public_key not in genesis_validator_public_keys
    assert not tuple(path for path in tmp_path.glob(".joining-node.*") if path.is_dir())


def _run(command: tuple[str, ...]) -> str:
    completed = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise AssertionError(f"command failed: {completed.stdout}{completed.stderr}")
    return completed.stdout


def _public_key_value(content: bytes) -> str:
    document: object = json.loads(content)
    if not isinstance(document, dict):
        raise AssertionError("validator key must be an object")
    public_key = document.get("pub_key")
    if not isinstance(public_key, dict):
        raise AssertionError("validator key must contain pub_key")
    value = public_key.get("value")
    if not isinstance(value, str):
        raise AssertionError("validator public key must contain a string value")
    return value
