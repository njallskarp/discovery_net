#!/usr/bin/env python3
"""Verify the public inspector certificate and one allowlisted read-only route."""

from __future__ import annotations

import argparse
import ipaddress
import socket
import ssl
import sys
import time
from collections.abc import Sequence
from typing import cast


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-address", required=True)
    parser.add_argument("--connect-host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--minimum-valid-seconds", type=int, default=86_400)
    parser.add_argument("--tls-mode", choices=("ip", "hostname"), required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser


def _name_values(name: object) -> list[str]:
    values: list[str] = []
    if not isinstance(name, tuple):
        return values
    for relative_name in name:
        if not isinstance(relative_name, tuple):
            continue
        for attribute in relative_name:
            if (
                isinstance(attribute, tuple)
                and len(attribute) == 2
                and isinstance(attribute[1], str)
            ):
                values.append(attribute[1])
    return values


def _validate_certificate(
    certificate: dict[str, object],
    *,
    address: str,
    tls_mode: str,
    minimum_valid_seconds: int,
) -> int:
    issuer = " ".join(_name_values(certificate.get("issuer")))
    if "Let's Encrypt" not in issuer:
        raise ValueError("certificate issuer is not Let's Encrypt")

    not_before = certificate.get("notBefore")
    not_after = certificate.get("notAfter")
    if not isinstance(not_before, str) or not isinstance(not_after, str):
        raise ValueError("certificate validity window is missing")
    starts_at = ssl.cert_time_to_seconds(not_before)
    expires_at = ssl.cert_time_to_seconds(not_after)
    now = time.time()
    remaining = int(expires_at - now)
    if starts_at > now + 300:
        raise ValueError("certificate is not valid yet")
    if remaining < minimum_valid_seconds:
        raise ValueError(
            f"certificate has only {remaining} seconds remaining; renewal is unhealthy"
        )

    if tls_mode == "ip":
        parsed_address = ipaddress.ip_address(address)
        if parsed_address.version != 4:
            raise ValueError("IP certificate mode currently requires a public IPv4 address")
        lifetime = int(expires_at - starts_at)
        if lifetime > 7 * 86_400:
            raise ValueError("IP certificate is not from the shortlived profile")
        alternatives = certificate.get("subjectAltName", ())
        if not isinstance(alternatives, tuple):
            raise ValueError("certificate subject alternative names are malformed")
        if ("IP Address", address) not in alternatives:
            raise ValueError("certificate does not contain the expected IP SAN")
    return remaining


def _check(args: argparse.Namespace) -> int:
    context = ssl.create_default_context()
    with (
        socket.create_connection(
            (args.connect_host, args.port), timeout=args.timeout
        ) as plain_socket,
        context.wrap_socket(plain_socket, server_hostname=args.expected_address) as tls_socket,
    ):
        certificate = cast(dict[str, object], tls_socket.getpeercert())
        remaining = _validate_certificate(
            certificate,
            address=args.expected_address,
            tls_mode=args.tls_mode,
            minimum_valid_seconds=args.minimum_valid_seconds,
        )
        request = (
            "GET /api/node HTTP/1.1\r\n"
            f"Host: {args.expected_address}\r\n"
            "Connection: close\r\n"
            "User-Agent: discovery-net-certificate-monitor/1\r\n\r\n"
        ).encode("ascii")
        tls_socket.sendall(request)
        response = tls_socket.recv(4096)
    status_line = response.partition(b"\r\n")[0]
    if not status_line.startswith(b"HTTP/1.1 200 "):
        raise ValueError(f"inspector health route failed: {status_line!r}")
    return remaining


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        remaining = _check(args)
    except (OSError, ValueError, ssl.SSLError) as error:
        print(f"inspector certificate check failed: {error}", file=sys.stderr)
        return 1
    print(f"inspector certificate healthy: remaining_seconds={remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
