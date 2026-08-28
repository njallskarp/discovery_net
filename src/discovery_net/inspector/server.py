# Serves inspector snapshots and browser assets over local read-only HTTP.

from __future__ import annotations

import json
from collections.abc import Callable
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Final, Self, final
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel

from discovery_net.inspector.service import InspectorService
from discovery_net.wire import parse_artifact_ref

_STATIC_TYPES: Final = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/inspector.css": ("inspector.css", "text/css; charset=utf-8"),
    "/inspector.js": ("inspector.js", "text/javascript; charset=utf-8"),
    "/vendor/cytoscape/cytoscape.min.js": (
        "vendor/cytoscape/cytoscape.min.js",
        "text/javascript; charset=utf-8",
    ),
    "/vendor/dompurify/purify.min.js": (
        "vendor/dompurify/purify.min.js",
        "text/javascript; charset=utf-8",
    ),
    "/vendor/katex/auto-render.min.js": (
        "vendor/katex/auto-render.min.js",
        "text/javascript; charset=utf-8",
    ),
    "/vendor/katex/katex.min.css": (
        "vendor/katex/katex.min.css",
        "text/css; charset=utf-8",
    ),
    "/vendor/katex/katex.min.js": (
        "vendor/katex/katex.min.js",
        "text/javascript; charset=utf-8",
    ),
    "/vendor/markdown-it/markdown-it.min.js": (
        "vendor/markdown-it/markdown-it.min.js",
        "text/javascript; charset=utf-8",
    ),
}
_CONTENT_SECURITY_POLICY: Final = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "base-uri 'none'; frame-ancestors 'none'"
)
_KATEX_FONT_TYPES: Final = {
    ".ttf": "font/ttf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


@final
class InspectorServer:
    """Hosts one local read-only inspector service and its browser interface."""

    __slots__ = ("_server",)

    def __init__(
        self,
        *,
        service: InspectorService,
        listen_host: str,
        listen_port: int,
    ) -> None:
        if not isinstance(service, InspectorService):
            raise TypeError("service must be an InspectorService")
        if not isinstance(listen_host, str):
            raise TypeError("listen_host must be a string")
        if not listen_host.strip():
            raise ValueError("listen_host must not be blank")
        if not isinstance(listen_port, int) or isinstance(listen_port, bool):
            raise TypeError("listen_port must be an integer")
        if not 0 <= listen_port <= 65535:
            raise ValueError("listen_port must be between 0 and 65535")

        handler = partial(_InspectorRequestHandler, service=service)
        self._server = ThreadingHTTPServer((listen_host, listen_port), handler)

    @property
    def listen_host(self) -> str:
        """Return the host bound by the local HTTP server."""
        host, _port = self._server.server_address[:2]
        return str(host)

    @property
    def listen_port(self) -> int:
        """Return the port bound by the local HTTP server."""
        _host, port = self._server.server_address[:2]
        return int(port)

    def serve_forever(self) -> None:
        """Serve requests until shutdown is requested."""
        self._server.serve_forever()

    def shutdown(self) -> None:
        """Stop a running serve loop."""
        self._server.shutdown()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_error: object) -> None:
        self._server.server_close()


class _InspectorRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args: object, service: InspectorService, **kwargs: object) -> None:
        self._service = service
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        path = request.path
        if path == "/api/snapshot":
            self._snapshot()
            return
        if path == "/api/node":
            self._model(self._service.node_snapshot)
            return
        if path == "/api/graph":
            self._graph(request.query)
            return
        if path == "/api/feed":
            self._feed(request.query)
            return
        contribution_prefix = "/api/contributions/"
        if path.startswith(contribution_prefix):
            self._contribution(path.removeprefix(contribution_prefix))
            return
        static = _STATIC_TYPES.get(path)
        if static is None:
            static = _katex_font(path)
        if static is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        name, content_type = static
        self._response(
            HTTPStatus.OK,
            _static_resource(name),
            content_type=content_type,
            cache_control="no-cache",
        )

    def do_POST(self) -> None:
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "read-only endpoint"})

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _snapshot(self) -> None:
        self._model(self._service.snapshot)

    def _graph(self, query: str) -> None:
        try:
            values = parse_qs(query, strict_parsing=True) if query else {}
            _require_query_fields(values, {"after_height"})
            after_height = _optional_query_integer(values, "after_height")
        except ValueError as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._model(lambda: self._service.knowledge_graph(after_height=after_height))

    def _feed(self, query: str) -> None:
        try:
            values = parse_qs(query, strict_parsing=True) if query else {}
            _require_query_fields(values, {"before", "limit"})
            before = _optional_feed_cursor(values)
            limit = _optional_query_integer(values, "limit")
            if limit is not None and not 1 <= limit <= 50:
                raise ValueError("limit must be between 1 and 50")
        except ValueError as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._model(
            lambda: self._service.feed_page(
                before=before,
                limit=20 if limit is None else limit,
            )
        )

    def _contribution(self, value: str) -> None:
        try:
            artifact_ref = parse_artifact_ref(value)
        except (TypeError, ValueError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid contribution reference"})
            return
        try:
            contribution = self._service.contribution(artifact_ref)
        except (OSError, TypeError, ValueError):
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "inspector data unavailable"},
            )
            return
        if contribution is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": "contribution not found"})
            return
        self._model(lambda: contribution)

    def _model(self, operation: Callable[[], BaseModel]) -> None:
        try:
            body = operation().model_dump_json().encode()
        except (OSError, TypeError, ValueError):
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "inspector data unavailable"},
            )
            return
        self._response(
            HTTPStatus.OK,
            body,
            content_type="application/json; charset=utf-8",
            cache_control="no-store",
        )

    def _json(self, status: HTTPStatus, value: object) -> None:
        self._response(
            status,
            json.dumps(value, separators=(",", ":")).encode(),
            content_type="application/json; charset=utf-8",
            cache_control="no-store",
        )

    def _response(
        self,
        status: HTTPStatus,
        body: bytes,
        *,
        content_type: str,
        cache_control: str,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def _static_resource(name: str) -> bytes:
    return files("discovery_net.inspector.static").joinpath(name).read_bytes()


def _katex_font(path: str) -> tuple[str, str] | None:
    prefix = "/vendor/katex/fonts/"
    if not path.startswith(prefix):
        return None
    filename = path.removeprefix(prefix)
    suffix = next(
        (suffix for suffix in _KATEX_FONT_TYPES if filename.endswith(suffix)),
        None,
    )
    if not filename or "/" in filename or suffix is None:
        return None
    return f"vendor/katex/fonts/{filename}", _KATEX_FONT_TYPES[suffix]


def _require_query_fields(values: dict[str, list[str]], allowed: set[str]) -> None:
    unexpected = set(values) - allowed
    if unexpected:
        raise ValueError(f"unexpected query field: {min(unexpected)}")


def _optional_query_integer(values: dict[str, list[str]], field_name: str) -> int | None:
    raw = values.get(field_name)
    if raw is None:
        return None
    if len(raw) != 1 or not raw[0].isdigit():
        raise ValueError(f"{field_name} must be a nonnegative integer")
    return int(raw[0])


def _optional_feed_cursor(values: dict[str, list[str]]) -> tuple[int, int] | None:
    raw = values.get("before")
    if raw is None:
        return None
    if len(raw) != 1:
        raise ValueError("before must be one feed cursor")
    parts = raw[0].split(":")
    if len(parts) != 2 or any(not part.isdigit() for part in parts):
        raise ValueError("before must be a height:transaction-index cursor")
    return int(parts[0]), int(parts[1])
