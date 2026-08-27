# Creates isolated single-node and multi-node CometBFT integration networks.

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import cast, final

from discovery_net.node import ArtifactLedgerSnapshot, LocalArtifactLedger
from discovery_net.node.runtime import (
    CometBFTGenesisWriter,
    CometBFTValidatorProvisioner,
    Endpoint,
    GenesisTrustAnchor,
    NodeLaunchSettings,
    PeerAdmissionPolicy,
)
from discovery_net.node.runtime._cometbft_config import _CometBFTConfig
from discovery_net.node.runtime._cometbft_home import _CometBFTHome
from discovery_net.node.runtime._cometbft_process import _CometBFTProcess
from discovery_net.node.runtime.genesis import _VerifiedGenesis
from tests.integration._integration_node import IntegrationNode

_CONVERGENCE_TIMEOUT_SECONDS = 20


@final
class IntegrationNetwork:
    """Owns an isolated CometBFT topology and its Discovery Net applications."""

    __slots__ = ("_chain_id", "_nodes", "_validator_count")

    def __init__(
        self,
        *,
        chain_id: str,
        nodes: tuple[IntegrationNode, ...],
        validator_count: int,
    ) -> None:
        self._chain_id = chain_id
        self._nodes = nodes
        self._validator_count = validator_count

    @property
    def chain_id(self) -> str:
        """Return the genesis chain identifier shared by every node."""
        return self._chain_id

    @property
    def nodes(self) -> tuple[IntegrationNode, ...]:
        """Return every node in deterministic testnet order."""
        return self._nodes

    @property
    def validators(self) -> tuple[IntegrationNode, ...]:
        """Return the nodes holding genesis validator keys."""
        return self._nodes[: self._validator_count]

    @classmethod
    def single(
        cls,
        *,
        binary: Path,
        root: Path,
        genesis_source: Path | None = None,
        ledger_path: Path | None = None,
    ) -> IntegrationNetwork:
        """Create one validator, optionally reusing genesis or application state."""
        home = root / "cometbft"
        _run((str(binary), "init", "--home", str(home)), "CometBFT initialization")
        if genesis_source is not None:
            shutil.copy2(genesis_source, home / "config" / "genesis.json")
        chain_id = _chain_id(home)
        ports = _available_ports(3)
        node = _node(
            binary=binary,
            home=home,
            ledger_path=ledger_path or root / "artifact-ledger.sqlite",
            chain_id=chain_id,
            name="node0",
            ports=ports,
            log_directory=root / "logs",
        )
        return cls(
            chain_id=chain_id,
            nodes=(node,),
            validator_count=1,
        )

    @classmethod
    def testnet(
        cls,
        *,
        binary: Path,
        root: Path,
        validators: int,
        non_validators: int = 0,
    ) -> IntegrationNetwork:
        """Create a shared-genesis network with independent local ports and ledgers."""
        homes_root = root / "cometbft"
        _run(
            (
                str(binary),
                "testnet",
                "--v",
                str(validators),
                "--n",
                "0",
                "--o",
                str(homes_root),
                "--populate-persistent-peers=false",
            ),
            "CometBFT testnet initialization",
        )
        total_nodes = validators + non_validators
        ports = _available_ports(total_nodes * 3)
        chain_id = _chain_id(homes_root / "node0")
        if non_validators:
            _prepare_joining_homes(
                binary=binary,
                homes_root=homes_root,
                genesis_path=homes_root / "node0" / "config" / "genesis.json",
                chain_id=chain_id,
                first_index=validators,
                count=non_validators,
                ports=ports,
            )
        nodes = tuple(
            _node(
                binary=binary,
                home=homes_root / f"node{index}",
                ledger_path=root / f"node{index}" / "artifact-ledger.sqlite",
                chain_id=chain_id,
                name=f"node{index}",
                ports=ports[index * 3 : index * 3 + 3],
                log_directory=root / "logs",
            )
            for index in range(total_nodes)
        )
        return cls(
            chain_id=chain_id,
            nodes=nodes,
            validator_count=validators,
        )

    @classmethod
    def formed(
        cls,
        *,
        binary: Path,
        root: Path,
        validators: int,
        chain_id: str = "discovery-formation-test",
    ) -> IntegrationNetwork:
        """Form a validator network exclusively through the production provisioning API."""
        provisioner = CometBFTValidatorProvisioner(binary=binary)
        homes_root = root / "cometbft"
        identities = tuple(
            provisioner.initialize_home(home=homes_root / f"node{index}")
            for index in range(validators)
        )
        genesis_validators = tuple(
            provisioner.genesis_validator(
                identity,
                name=f"node{index}",
                voting_power=10,
            )
            for index, identity in enumerate(identities)
        )
        genesis_path = root / "genesis.json"
        trust_anchor = CometBFTGenesisWriter(binary=binary).write(
            path=genesis_path,
            chain_id=chain_id,
            genesis_time=datetime.now(UTC),
            validators=genesis_validators,
        )
        for identity in identities:
            provisioner.install_genesis(
                identity=identity,
                genesis_path=genesis_path,
                genesis_trust_anchor=trust_anchor,
            )

        ports = _available_ports(validators * 3)
        nodes = tuple(
            _node(
                binary=binary,
                home=homes_root / f"node{index}",
                ledger_path=root / f"node{index}" / "artifact-ledger.sqlite",
                chain_id=chain_id,
                name=f"node{index}",
                ports=ports[index * 3 : index * 3 + 3],
                log_directory=root / "logs",
            )
            for index in range(validators)
        )
        return cls(
            chain_id=chain_id,
            nodes=nodes,
            validator_count=validators,
        )

    def start_all(
        self,
        *,
        create_empty_blocks: bool = False,
        peer_groups: tuple[tuple[int, ...], ...] | None = None,
    ) -> None:
        """Start every application and CometBFT node in the requested topology."""
        for node in self._nodes:
            node.start_application()
        self.start_all_cometbft(
            create_empty_blocks=create_empty_blocks,
            peer_groups=peer_groups,
        )

    def start_all_cometbft(
        self,
        *,
        create_empty_blocks: bool = False,
        peer_groups: tuple[tuple[int, ...], ...] | None = None,
    ) -> None:
        """Start consensus for applications that are already running."""
        memberships = _peer_memberships(len(self._nodes), peer_groups)
        for index, node in enumerate(self._nodes):
            peers = tuple(
                self._nodes[peer_index].peer_address
                for peer_index in memberships[index]
                if peer_index != index
            )
            node.start_cometbft(
                peers=peers,
                create_empty_blocks=create_empty_blocks,
                wait_until_ready=False,
            )
        for node in self._nodes:
            node.wait_for_rpc()
        for node in self._nodes:
            node.wait_for_consensus_ready()

    def stop_all_cometbft(self) -> None:
        """Stop every CometBFT process while leaving applications running."""
        for node in reversed(self._nodes):
            node.stop_cometbft()

    def stop_all(self) -> None:
        """Stop every consensus process and application."""
        for node in reversed(self._nodes):
            node.close()

    def wait_for_convergence(
        self,
        *,
        minimum_entries: int,
        timeout_seconds: float = _CONVERGENCE_TIMEOUT_SECONDS,
    ) -> tuple[ArtifactLedgerSnapshot, ...]:
        """Wait until every node persists the same ordered ledger and state hash."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for node in self._nodes:
                node.assert_running()
            snapshots = tuple(node.snapshot() for node in self._nodes)
            if all(
                snapshot is not None and len(snapshot.entries) >= minimum_entries
                for snapshot in snapshots
            ):
                present = cast(tuple[ArtifactLedgerSnapshot, ...], snapshots)
                entries = present[0].entries
                height = present[0].height
                state_hash = LocalArtifactLedger(entries=entries).state_hash()
                if all(
                    snapshot.height == height
                    and snapshot.entries == entries
                    and LocalArtifactLedger(entries=snapshot.entries).state_hash() == state_hash
                    for snapshot in present[1:]
                ):
                    return present
            time.sleep(0.05)
        diagnostics = "\n".join(f"{node.name}:\n{node.diagnostics()}" for node in self._nodes)
        raise AssertionError(
            f"network did not converge with {minimum_entries} entries\n{diagnostics}"
        )

    def __enter__(self) -> IntegrationNetwork:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.stop_all()


def _node(
    *,
    binary: Path,
    home: Path,
    ledger_path: Path,
    chain_id: str,
    name: str,
    ports: tuple[int, ...],
    log_directory: Path,
) -> IntegrationNode:
    node_id = _run(
        (str(binary), "show-node-id", "--home", str(home)),
        "CometBFT node ID lookup",
    ).strip()
    application_port, rpc_port, p2p_port = ports
    return IntegrationNode(
        name=name,
        binary=binary,
        home=home,
        ledger_path=ledger_path,
        chain_id=chain_id,
        node_id=node_id,
        application_address=f"127.0.0.1:{application_port}",
        rpc_address=f"127.0.0.1:{rpc_port}",
        p2p_address=f"127.0.0.1:{p2p_port}",
        log_directory=log_directory,
    )


def _chain_id(home: Path) -> str:
    value: object = json.loads((home / "config" / "genesis.json").read_bytes())
    if not isinstance(value, dict):
        raise ValueError("CometBFT genesis must be a JSON object")
    chain_id = value.get("chain_id")
    if not isinstance(chain_id, str) or not chain_id:
        raise ValueError("CometBFT genesis must contain a chain ID")
    return chain_id


def _prepare_joining_homes(
    *,
    binary: Path,
    homes_root: Path,
    genesis_path: Path,
    chain_id: str,
    first_index: int,
    count: int,
    ports: tuple[int, ...],
) -> None:
    genesis_content = genesis_path.read_bytes()
    trust_anchor = GenesisTrustAnchor(
        expected_chain_id=chain_id,
        expected_sha256=hashlib.sha256(genesis_content).hexdigest(),
    )
    verified = _VerifiedGenesis.from_path(
        path=genesis_path,
        trust_anchor=trust_anchor,
    )
    process = _CometBFTProcess(binary=binary)
    process.require_compatible_command_surface()

    for index in range(first_index, first_index + count):
        application_port, rpc_port, p2p_port = ports[index * 3 : index * 3 + 3]
        settings = NodeLaunchSettings(
            home=homes_root / f"node{index}",
            moniker=f"node{index}",
            genesis_path=genesis_path,
            genesis_trust_anchor=trust_anchor,
            abci_endpoint=Endpoint(host="127.0.0.1", port=application_port),
            rpc_listen_endpoint=Endpoint(host="127.0.0.1", port=rpc_port),
            p2p_listen_endpoint=Endpoint(host="127.0.0.1", port=p2p_port),
            p2p_advertised_endpoint=Endpoint(host="127.0.0.1", port=p2p_port),
            peer_exchange=False,
            peer_admission=PeerAdmissionPolicy(
                address_book_strict=False,
                allow_duplicate_ip=True,
            ),
            create_empty_blocks=False,
            log_level="error",
        )
        _CometBFTHome(
            path=settings.home,
            config=_CometBFTConfig(),
            process=process,
        ).prepare(genesis=verified, settings=settings)


def _peer_memberships(
    node_count: int,
    groups: tuple[tuple[int, ...], ...] | None,
) -> tuple[tuple[int, ...], ...]:
    if groups is None:
        all_nodes = tuple(range(node_count))
        return tuple(all_nodes for _ in range(node_count))
    memberships: list[tuple[int, ...] | None] = [None] * node_count
    for group in groups:
        for index in group:
            if not 0 <= index < node_count:
                raise ValueError("peer group contains an unknown node")
            if memberships[index] is not None:
                raise ValueError("node belongs to more than one peer group")
            memberships[index] = group
    if any(membership is None for membership in memberships):
        raise ValueError("every node must belong to one peer group")
    return cast(tuple[tuple[int, ...], ...], tuple(memberships))


def _available_ports(count: int) -> tuple[int, ...]:
    listeners: list[socket.socket] = []
    try:
        for _ in range(count):
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listeners.append(listener)
        return tuple(int(listener.getsockname()[1]) for listener in listeners)
    finally:
        for listener in listeners:
            listener.close()


def _run(command: tuple[str, ...], description: str) -> str:
    completed = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"{description} failed with code {completed.returncode}"
            f"\n{completed.stdout}{completed.stderr}"
        )
    return completed.stdout
