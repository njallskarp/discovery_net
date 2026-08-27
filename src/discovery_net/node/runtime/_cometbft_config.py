# Applies and verifies the CometBFT configuration owned by Discovery Net.

from __future__ import annotations

import os
import stat
import tempfile
import tomllib
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import cast, final

import tomlkit

from discovery_net.node.runtime.node_launch_settings import NodeLaunchSettings


@final
class _CometBFTConfig:
    """Writes the complete supported runtime configuration without touching identity."""

    __slots__ = ()

    def apply_and_verify(self, *, path: Path, settings: NodeLaunchSettings) -> None:
        """Atomically apply settings and verify their parsed on-disk representation."""
        try:
            document = tomlkit.parse(path.read_text())
        except (OSError, tomlkit.exceptions.ParseError) as error:
            raise ValueError("CometBFT configuration could not be parsed") from error

        document["moniker"] = settings.moniker
        document["proxy_app"] = str(settings.abci_endpoint)
        document["abci"] = "grpc"
        document["log_level"] = settings.log_level

        rpc = _mutable_table(document, "rpc")
        rpc["laddr"] = settings.rpc_listen_endpoint.tcp_url()
        rpc["unsafe"] = False
        rpc["cors_allowed_origins"] = []
        rpc["grpc_laddr"] = ""
        rpc["pprof_laddr"] = ""

        p2p = _mutable_table(document, "p2p")
        p2p["laddr"] = settings.p2p_listen_endpoint.tcp_url()
        p2p["external_address"] = (
            str(settings.p2p_advertised_endpoint)
            if settings.p2p_advertised_endpoint is not None
            else ""
        )
        p2p["persistent_peers"] = ",".join(str(peer) for peer in settings.persistent_peers)
        p2p["pex"] = settings.peer_exchange
        p2p["addr_book_strict"] = settings.peer_admission.address_book_strict
        p2p["allow_duplicate_ip"] = settings.peer_admission.allow_duplicate_ip

        consensus = _mutable_table(document, "consensus")
        consensus["create_empty_blocks"] = settings.create_empty_blocks

        rendered = tomlkit.dumps(document).encode()
        try:
            rendered_document = tomllib.loads(rendered.decode())
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise ValueError("rendered CometBFT configuration could not be parsed") from error
        _require_settings(rendered_document, settings)
        _replace_file(path, rendered)
        self.verify(path=path, settings=settings)

    def verify(self, *, path: Path, settings: NodeLaunchSettings) -> None:
        """Reject a configuration that does not encode the requested runtime settings."""
        try:
            document = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise ValueError("written CometBFT configuration could not be parsed") from error

        _require_settings(document, settings)


def _require_settings(document: Mapping[str, object], settings: NodeLaunchSettings) -> None:
    expected_base: Mapping[str, object] = {
        "moniker": settings.moniker,
        "proxy_app": str(settings.abci_endpoint),
        "abci": "grpc",
        "log_level": settings.log_level,
    }
    expected_rpc: Mapping[str, object] = {
        "laddr": settings.rpc_listen_endpoint.tcp_url(),
        "unsafe": False,
        "cors_allowed_origins": [],
        "grpc_laddr": "",
        "pprof_laddr": "",
    }
    expected_p2p: Mapping[str, object] = {
        "laddr": settings.p2p_listen_endpoint.tcp_url(),
        "external_address": (
            str(settings.p2p_advertised_endpoint)
            if settings.p2p_advertised_endpoint is not None
            else ""
        ),
        "persistent_peers": ",".join(str(peer) for peer in settings.persistent_peers),
        "pex": settings.peer_exchange,
        "addr_book_strict": settings.peer_admission.address_book_strict,
        "allow_duplicate_ip": settings.peer_admission.allow_duplicate_ip,
    }
    _require_values(document, expected_base, "base")
    _require_values(_table(document, "rpc"), expected_rpc, "rpc")
    _require_values(_table(document, "p2p"), expected_p2p, "p2p")
    _require_values(
        _table(document, "consensus"),
        {"create_empty_blocks": settings.create_empty_blocks},
        "consensus",
    )


def _mutable_table(document: MutableMapping[str, object], name: str) -> MutableMapping[str, object]:
    value = document.get(name)
    if not isinstance(value, MutableMapping):
        raise ValueError(f"CometBFT configuration is missing the {name} table")
    return cast(MutableMapping[str, object], value)


def _table(document: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = document.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"CometBFT configuration is missing the {name} table")
    return cast(Mapping[str, object], value)


def _require_values(
    actual: Mapping[str, object],
    expected: Mapping[str, object],
    section: str,
) -> None:
    for key, expected_value in expected.items():
        if actual.get(key) != expected_value:
            raise ValueError(f"CometBFT {section} configuration did not preserve {key}")


def _replace_file(path: Path, content: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, path)
        _sync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
