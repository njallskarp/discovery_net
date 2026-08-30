#!/usr/bin/env python3
"""Assert the adapted Caddy configuration is HTTPS-only and read-only."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from typing import Any

_LE_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
_ALLOWED_PATHS = {
    "/",
    "/index.html",
    "/inspector.css",
    "/inspector.js",
    "/vendor/cytoscape/cytoscape.min.js",
    "/vendor/dompurify/purify.min.js",
    "/vendor/katex/auto-render.min.js",
    "/vendor/katex/katex.min.css",
    "/vendor/katex/katex.min.js",
    "/vendor/katex/fonts/*",
    "/vendor/markdown-it/markdown-it.min.js",
    "/api/snapshot",
    "/api/node",
    "/api/graph",
    "/api/feed",
    "/api/contributions/*",
}


def _walk(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _fail(message: str) -> None:
    raise SystemExit(f"caddy security check failed: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("ip", "hostname"), required=True)
    parser.add_argument("--address", required=True)
    args = parser.parse_args()
    document = json.load(sys.stdin)

    if document.get("admin") != {"disabled": True}:
        _fail("the Caddy admin API must be disabled")
    automation = document["apps"]["tls"]["automation"]
    if automation.get("renew_interval", 0) > 600_000_000_000:
        _fail("certificate renewal scans must run at least every ten minutes")
    policies = automation.get("policies", [])
    if len(policies) != 1 or policies[0].get("subjects") != [args.address]:
        _fail("TLS automation must cover exactly the configured inspector address")
    issuers = policies[0].get("issuers", [])
    if len(issuers) != 1:
        _fail("TLS must have exactly one issuer; fallback issuers are prohibited")
    issuer = issuers[0]
    if issuer.get("module") != "acme" or issuer.get("ca") != _LE_DIRECTORY:
        _fail("TLS issuer must be Let's Encrypt ACME")
    if not issuer.get("email"):
        _fail("ACME contact email is missing")
    if args.mode == "ip" and issuer.get("profile") != "shortlived":
        _fail("IP mode must use the shortlived profile")
    if args.mode == "hostname" and "profile" in issuer:
        _fail("hostname mode must use normal hostname certificate issuance")

    servers = document["apps"]["http"]["servers"]
    if len(servers) != 1:
        _fail("expected exactly one HTTPS server")
    server = next(iter(servers.values()))
    if server.get("listen") != [":443"]:
        _fail("configured application server must listen only on HTTPS")
    if server.get("protocols") != ["h1", "h2"]:
        _fail("only HTTP/1.1 and HTTP/2 are permitted")
    if server.get("max_header_bytes", 0) > 16_000:
        _fail("request header limit is too large")

    nodes = list(_walk(server))
    proxies = [node for node in nodes if node.get("handler") == "reverse_proxy"]
    if len(proxies) != 1 or proxies[0].get("upstreams") != [{"dial": "inspector:8765"}]:
        _fail("proxy may forward only to the inspector")
    body_limits = [node.get("max_size") for node in nodes if node.get("handler") == "request_body"]
    if body_limits != [1000]:
        _fail("read-only routes must have a 1 KB request-body limit")

    path_sets = [set(node["path"]) for node in nodes if "path" in node]
    if _ALLOWED_PATHS not in path_sets:
        _fail("public path allowlist does not match audited inspector routes")
    method_sets = [node["method"] for node in nodes if "method" in node]
    if method_sets != [["GET"]]:
        _fail("proxy must permit only GET")
    statuses = {
        node.get("status_code") for node in nodes if node.get("handler") == "static_response"
    }
    if not {404, 405}.issubset(statuses):
        _fail("unintended routes and non-GET methods must be rejected")

    rendered = json.dumps(document)
    for required in (
        "Strict-Transport-Security",
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
    ):
        if required not in rendered:
            _fail(f"missing security header: {required}")
    if '"module": "internal"' in rendered:
        _fail("self-signed certificate fallback is prohibited")

    print(f"caddy {args.mode} HTTPS contract valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
