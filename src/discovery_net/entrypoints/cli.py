# Submits knowledge-graph contributions through a local Discovery Net node.

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pydantic import BaseModel, ConfigDict

from discovery_net.knowledge_graph import ArtifactRef, Contribution, ContributionKind
from discovery_net.submission import ArtifactSubmitter, SubmissionError
from discovery_net.wire import parse_artifact_ref

_DEFAULT_COMETBFT_RPC_URL = "http://127.0.0.1:26657"


class _SubmissionOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_ref: ArtifactRef
    accepted_for_broadcast: bool


def main(arguments: Sequence[str] | None = None) -> int:
    """Submit one contribution and return a process exit code."""
    parsed = _argument_parser().parse_args(arguments)
    try:
        private_key = _load_private_key(parsed.private_key)
        contribution = Contribution(
            kind=parsed.kind,
            title=parsed.title,
            body=parsed.body,
            created_at=datetime.now(UTC),
            parent=parsed.parent,
        )
        receipt = ArtifactSubmitter(
            private_key=private_key,
            cometbft_rpc_url=parsed.rpc_url,
        ).submit(contribution)
    except (OSError, TypeError, ValueError, SubmissionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(
        _SubmissionOutput(
            artifact_ref=receipt.artifact_ref,
            accepted_for_broadcast=receipt.accepted,
        ).model_dump_json()
    )
    return 0 if receipt.accepted else 1


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="discovery-net",
        description="Interact with a local Discovery Net node.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser(
        "submit",
        help="submit a contribution",
        description="Submit a contribution through a local Discovery Net node.",
    )
    submit.add_argument(
        "--private-key",
        required=True,
        type=Path,
        help="path to an unencrypted Ed25519 PEM private key",
    )
    submit.add_argument(
        "--kind",
        required=True,
        type=ContributionKind,
        choices=tuple(ContributionKind),
        help="mathematical or organizational role of the contribution",
    )
    submit.add_argument("--title", required=True, help="short contribution title")
    submit.add_argument("--body", required=True, help="contribution body")
    submit.add_argument(
        "--parent",
        type=_artifact_reference,
        help="canonical artifact reference of the parent contribution",
    )
    submit.add_argument(
        "--rpc-url",
        default=_DEFAULT_COMETBFT_RPC_URL,
        help=f"local CometBFT RPC URL (default: {_DEFAULT_COMETBFT_RPC_URL})",
    )
    return parser


def _artifact_reference(value: str) -> ArtifactRef:
    try:
        return parse_artifact_ref(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    encoded = path.read_bytes()
    try:
        private_key = load_pem_private_key(encoded, password=None)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "private key file must contain an unencrypted Ed25519 PEM private key"
        ) from error
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("private key file must contain an Ed25519 private key")
    return private_key


if __name__ == "__main__":
    raise SystemExit(main())
