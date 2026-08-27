# Serves inspector snapshots and browser assets over local read-only HTTP.

from __future__ import annotations

import json
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Final, Self, final
from urllib.parse import urlsplit

from discovery_net.inspector.service import InspectorService

_STATIC_TYPES: Final = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/inspector.css": ("inspector.css", "text/css; charset=utf-8"),
    "/inspector.js": ("inspector.js", "text/javascript; charset=utf-8"),
}
_CONTENT_SECURITY_POLICY: Final = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
)


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
        path = urlsplit(self.path).path
        if path == "/api/snapshot":
            self._snapshot()
            return
        static = _STATIC_TYPES.get(path)
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
        try:
            body = self._service.snapshot().model_dump_json().encode()
        except (OSError, TypeError, ValueError):
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "inspector snapshot unavailable"},
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
