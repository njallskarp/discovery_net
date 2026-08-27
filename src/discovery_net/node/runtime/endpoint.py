# Defines one explicit TCP endpoint used by the local CometBFT runtime.

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Self
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True, kw_only=True)
class Endpoint:
    """Identifies one TCP host and port without implying an exposure policy."""

    host: str
    port: int

    def __post_init__(self) -> None:
        if not isinstance(self.host, str):
            raise TypeError("host must be a string")
        if not self.host or self.host != self.host.strip():
            raise ValueError("host must not be blank or padded")
        if any(character.isspace() for character in self.host):
            raise ValueError("host must not contain whitespace")
        if any(character in self.host for character in "/@[]"):
            raise ValueError("host must not contain endpoint delimiters")
        if ":" in self.host:
            try:
                address = ip_address(self.host)
            except ValueError as error:
                raise ValueError("hosts containing colons must be IPv6 addresses") from error
            if address.version != 6:
                raise ValueError("hosts containing colons must be IPv6 addresses")
        if not isinstance(self.port, int) or isinstance(self.port, bool):
            raise TypeError("port must be an integer")
        if not 1 <= self.port <= 65_535:
            raise ValueError("port must be between 1 and 65535")

    @classmethod
    def parse(cls, value: str) -> Self:
        """Parse a host-and-port authority into an endpoint."""
        if not isinstance(value, str):
            raise TypeError("endpoint must be a string")
        if not value or value != value.strip():
            raise ValueError("endpoint must not be blank or padded")

        parsed = urlsplit(f"//{value}")
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("endpoint must contain only a host and port")
        try:
            host = parsed.hostname
            port = parsed.port
        except ValueError as error:
            raise ValueError("endpoint must contain a valid port") from error
        if host is None or port is None:
            raise ValueError("endpoint must contain a host and port")
        return cls(host=host, port=port)

    @property
    def is_unspecified(self) -> bool:
        """Return whether the host denotes every local network interface."""
        try:
            return ip_address(self.host).is_unspecified
        except ValueError:
            return False

    def tcp_url(self) -> str:
        """Render the endpoint in CometBFT's TCP URL form."""
        return f"tcp://{self}"

    def __str__(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"
