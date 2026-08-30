#!/usr/bin/env python3
"""Assert the resolved cloud Compose security boundary."""

from __future__ import annotations

import json
import sys
from typing import Any


def _fail(message: str) -> None:
    raise SystemExit(f"compose security check failed: {message}")


def _assert_hardened(name: str, service: dict[str, Any]) -> None:
    user = str(service.get("user", ""))
    if not user or user.split(":", maxsplit=1)[0] in {"", "0", "root"}:
        _fail(f"{name} must run as an explicit non-root user")
    if service.get("read_only") is not True:
        _fail(f"{name} must use a read-only root filesystem")
    if service.get("cap_drop") != ["ALL"]:
        _fail(f"{name} must drop all Linux capabilities")
    if "no-new-privileges:true" not in service.get("security_opt", []):
        _fail(f"{name} must set no-new-privileges")
    if not service.get("pids_limit"):
        _fail(f"{name} must have a PID limit")
    if not service.get("cpus") or not service.get("mem_limit"):
        _fail(f"{name} must have CPU and memory limits")
    log_options = service.get("logging", {}).get("options", {})
    if not {"max-file", "max-size"}.issubset(log_options):
        _fail(f"{name} must have bounded logs")


def _published_ports(service: dict[str, Any]) -> set[tuple[str, str, int]]:
    return {
        (
            str(port.get("host_ip", "")),
            str(port.get("published", "")),
            int(port["target"]),
        )
        for port in service.get("ports", [])
    }


def main() -> int:
    document = json.load(sys.stdin)
    services = document["services"]

    for name in (
        "application",
        "cometbft",
        "rpc",
        "p2p-gateway",
        "inspector",
        "caddy",
        "inspector-cert-monitor",
    ):
        _assert_hardened(name, services[name])

    if services["caddy"].get("cap_add") != ["NET_BIND_SERVICE"]:
        _fail("caddy may add only NET_BIND_SERVICE")
    for name in (
        "application",
        "cometbft",
        "rpc",
        "p2p-gateway",
        "inspector",
        "inspector-cert-monitor",
    ):
        if services[name].get("cap_add"):
            _fail(f"{name} must not add capabilities")

    all_ports = {
        (name, *port) for name, service in services.items() for port in _published_ports(service)
    }
    expected_ports = {
        ("caddy", "0.0.0.0", "80", 80),
        ("caddy", "0.0.0.0", "443", 443),
        ("p2p-gateway", "0.0.0.0", "26656", 8080),
        ("rpc", "127.0.0.1", "26657", 8080),
    }
    if all_ports != expected_ports:
        _fail(f"unexpected published ports: {sorted(all_ports)}")

    inspector_volumes = services["inspector"].get("volumes", [])
    if len(inspector_volumes) != 1:
        _fail("inspector must have exactly one mount")
    ledger_mount = inspector_volumes[0]
    if (
        ledger_mount.get("target") != "/var/lib/discovery-net"
        or ledger_mount.get("read_only") is not True
    ):
        _fail("inspector ledger mount must be read-only")

    for name in ("caddy", "inspector-cert-monitor"):
        for volume in services[name].get("volumes", []):
            target = str(volume.get("target", "")).lower()
            if any(token in target for token in ("ledger", "comet", "key", "state")):
                _fail(f"{name} has a prohibited node-data mount: {target}")

    if set(services["caddy"].get("networks", {})) != {"edge"}:
        _fail("caddy must attach only to the edge network")
    if set(services["inspector-cert-monitor"].get("networks", {})) != {"edge"}:
        _fail("certificate monitor must attach only to the edge network")
    if set(services["inspector"].get("networks", {})) != {"private", "edge"}:
        _fail("inspector must attach only to private and edge networks")
    if document["networks"]["private"].get("internal") is not True:
        _fail("private network must remain internal")

    print("compose security contract valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
