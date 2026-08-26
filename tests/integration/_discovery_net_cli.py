# Invokes the production CLI as an isolated integration-test process.

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Self, final

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr, ValidationError, field_validator

from discovery_net.knowledge_graph import ArtifactRef, ContributionKind
from discovery_net.wire import parse_artifact_ref

_CLI_TIMEOUT_SECONDS = 15


class _SubmissionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifact_ref: StrictStr
    accepted_for_broadcast: StrictBool

    @field_validator("artifact_ref")
    @classmethod
    def validate_artifact_ref(cls, value: str) -> str:
        parse_artifact_ref(value)
        return value


@final
class DiscoveryNetCLI:
    """Runs the production contribution command against one CometBFT RPC endpoint."""

    __slots__ = ("_private_key_path", "_rpc_url")

    def __init__(self, *, rpc_url: str, private_key_path: Path) -> None:
        self._rpc_url = rpc_url
        self._private_key_path = private_key_path

    @classmethod
    def with_private_key(
        cls,
        *,
        rpc_url: str,
        directory: Path,
        private_key: Ed25519PrivateKey,
    ) -> Self:
        """Create a CLI driver backed by a temporary PEM identity."""
        private_key_path = directory / "agent.pem"
        private_key_path.write_bytes(
            private_key.private_bytes(
                Encoding.PEM,
                PrivateFormat.PKCS8,
                NoEncryption(),
            )
        )
        return cls(rpc_url=rpc_url, private_key_path=private_key_path)

    def submit(
        self,
        *,
        kind: ContributionKind,
        title: str,
        body: str,
        parent: ArtifactRef | None = None,
    ) -> ArtifactRef:
        """Submit one contribution and return its validated artifact reference."""
        command = [
            sys.executable,
            "-m",
            "discovery_net.entrypoints.cli",
            "submit",
            "--private-key",
            str(self._private_key_path),
            "--kind",
            kind.value,
            "--title",
            title,
            "--body",
            body,
            "--rpc-url",
            self._rpc_url,
        ]
        if parent is not None:
            command.extend(("--parent", parent))

        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                timeout=_CLI_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise AssertionError(
                f"Discovery Net CLI did not finish within {_CLI_TIMEOUT_SECONDS} seconds"
            ) from error
        if completed.returncode != 0:
            raise AssertionError(
                f"Discovery Net CLI exited with {completed.returncode}\n"
                f"stdout:\n{completed.stdout.decode(errors='replace')}\n"
                f"stderr:\n{completed.stderr.decode(errors='replace')}"
            )
        try:
            output = _SubmissionOutput.model_validate_json(completed.stdout)
        except ValidationError as error:
            raise AssertionError(
                "Discovery Net CLI returned an invalid submission result"
            ) from error
        if not output.accepted_for_broadcast:
            raise AssertionError("Discovery Net CLI did not report CheckTx acceptance")
        return ArtifactRef(output.artifact_ref)
