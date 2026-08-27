# Exercises isolated node lifecycles over a real Docker P2P transport.

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from tests.docker._localnet import (
    DockerNode,
    available_ports,
    build_image,
    create_p2p_network,
    initialize_validator,
    remove_image,
    remove_p2p_network,
    wait_for_matching_entries,
)
from tests.integration._transactions import signed_transaction

pytestmark = pytest.mark.skipif(
    os.environ.get("DISCOVERY_NET_RUN_DOCKER_TESTS") != "1",
    reason="live Docker tests run only in the dedicated integration job",
)


def test_independent_docker_nodes_are_isolated_durable_and_convergent(tmp_path: Path) -> None:
    """Prove join, PEX, RPC isolation, restart durability, and post-failure consensus."""
    suffix = uuid4().hex[:8]
    image = f"discovery-net-node:docker-test-{suffix}"
    p2p_network = f"discovery-net-p2p-{suffix}"
    projects = tuple(f"discovery-net-{name}-{suffix}" for name in ("validator", "bridge", "peer"))
    ports = available_ports(4)
    nodes: list[DockerNode] = []

    try:
        build_image(image)
        create_p2p_network(p2p_network)
        validator_data = tmp_path / "validator" / "cometbft"
        initialize_validator(image=image, data_directory=validator_data)
        genesis_path = validator_data / "cometbft" / "config" / "genesis.json"
        genesis_content = genesis_path.read_bytes()
        genesis_document = json.loads(genesis_content)
        assert isinstance(genesis_document, dict)
        chain_id = genesis_document["chain_id"]
        assert isinstance(chain_id, str)
        genesis_sha256 = hashlib.sha256(genesis_content).hexdigest()

        validator = DockerNode(
            project=projects[0],
            image=image,
            root=tmp_path / "validator",
            chain_id=chain_id,
            genesis_path=genesis_path,
            genesis_sha256=genesis_sha256,
            p2p_alias=f"validator-{suffix}",
            p2p_network=p2p_network,
            rpc_port=ports[0],
        )
        nodes.append(validator)
        validator.start()

        bridge = DockerNode(
            project=projects[1],
            image=image,
            root=tmp_path / "bridge",
            chain_id=chain_id,
            genesis_path=genesis_path,
            genesis_sha256=genesis_sha256,
            p2p_alias=f"bridge-{suffix}",
            p2p_network=p2p_network,
            rpc_port=ports[1],
            persistent_peers=f"{validator.node_id()}@{validator.p2p_alias}:26656",
        )
        nodes.append(bridge)
        bridge.start()
        bridge.wait_for_peers(frozenset({validator.project}))

        peer = DockerNode(
            project=projects[2],
            image=image,
            root=tmp_path / "peer",
            chain_id=chain_id,
            genesis_path=genesis_path,
            genesis_sha256=genesis_sha256,
            p2p_alias=f"peer-{suffix}",
            p2p_network=p2p_network,
            rpc_port=ports[2],
            persistent_peers=f"{bridge.node_id()}@{bridge.p2p_alias}:26656",
        )
        nodes.append(peer)
        peer.start()
        peer.wait_for_peers(frozenset({validator.project, bridge.project}))

        assert validator.rpc.broadcast_commit(signed_transaction(chain_id, "Docker join")) > 0
        wait_for_matching_entries((validator, bridge, peer), minimum_entries=1)
        peer.assert_remote_rpc_is_unreachable(validator.p2p_alias, validator.rpc_port)
        _assert_runtime_boundaries(validator)

        peer_id = peer.node_id()
        bridge.stop()
        peer.wait_for_peers(frozenset({validator.project}))
        assert validator.rpc.broadcast_commit(signed_transaction(chain_id, "After bridge")) > 0
        wait_for_matching_entries((validator, peer), minimum_entries=2)

        peer.stop()
        peer.start()
        peer.wait_for_peers(frozenset({validator.project}))
        assert peer.node_id() == peer_id
        wait_for_matching_entries((validator, peer), minimum_entries=2)

        invalid = DockerNode(
            project=f"discovery-net-invalid-{suffix}",
            image=image,
            root=tmp_path / "invalid",
            chain_id=chain_id,
            genesis_path=genesis_path,
            genesis_sha256="0" * 64,
            p2p_alias=f"invalid-{suffix}",
            p2p_network=p2p_network,
            rpc_port=ports[3],
        )
        nodes.append(invalid)
        result = invalid.run_cometbft_once()
        assert result.returncode != 0
        assert not any(invalid.cometbft_data_directory.iterdir())
    finally:
        for node in reversed(nodes):
            node.stop()
        remove_p2p_network(p2p_network)
        remove_image(image)


def _assert_runtime_boundaries(node: DockerNode) -> None:
    application = node.inspect_service("application")
    cometbft = node.inspect_service("cometbft")
    rpc = node.inspect_service("rpc")

    for service in (application, cometbft, rpc):
        host_config = service["HostConfig"]
        assert isinstance(host_config, dict)
        assert host_config["ReadonlyRootfs"] is True
        assert host_config["CapDrop"] == ["ALL"]
        assert "no-new-privileges:true" in host_config["SecurityOpt"]

    comet_ports = cometbft["NetworkSettings"]
    assert isinstance(comet_ports, dict)
    assert not comet_ports["Ports"]

    rpc_network = rpc["NetworkSettings"]
    assert isinstance(rpc_network, dict)
    published_rpc = rpc_network["Ports"]
    assert isinstance(published_rpc, dict)
    bindings = published_rpc["8080/tcp"]
    assert isinstance(bindings, list) and bindings[0]["HostIp"] == "127.0.0.1"
