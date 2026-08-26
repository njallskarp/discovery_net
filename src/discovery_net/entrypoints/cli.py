# Provides the command-line interface to a local Discovery Net node.

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pydantic import BaseModel, ConfigDict

from discovery_net.indexing import IndexedArtifact, KnowledgeGraphIndex
from discovery_net.knowledge_graph import (
    ArtifactRef,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.node import SQLiteArtifactLedgerStore
from discovery_net.query import KnowledgeGraphQueries
from discovery_net.submission import ArtifactSubmitter, SubmissionError
from discovery_net.wire import PayloadType, parse_artifact_ref

_DEFAULT_COMETBFT_RPC_URL = "http://127.0.0.1:26657"


class _SubmissionOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_ref: ArtifactRef
    accepted_for_broadcast: bool


class _ArtifactOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_ref: ArtifactRef
    payload_type: PayloadType
    artifact: Contribution | ContributionRelation
    chain_id: str
    signer_public_key: str
    signature: str
    height: int
    transaction_index: int

    @classmethod
    def from_indexed(cls, indexed: IndexedArtifact) -> _ArtifactOutput:
        entry = indexed.ledger_entry
        envelope = entry.envelope
        return cls(
            artifact_ref=indexed.artifact_ref,
            payload_type=envelope.payload_type,
            artifact=indexed.artifact,
            chain_id=envelope.chain_id,
            signer_public_key=envelope.signer_public_key.hex(),
            signature=envelope.signature.hex(),
            height=entry.height,
            transaction_index=entry.transaction_index,
        )


class _QueryOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    indexed_height: int
    artifacts: tuple[_ArtifactOutput, ...]


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one Discovery Net command and return its process exit code."""
    parsed = _argument_parser().parse_args(arguments)
    try:
        if parsed.command == "submit":
            return _submit(parsed)
        return _query(parsed)
    except (OSError, sqlite3.Error, TypeError, ValueError, SubmissionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _submit(arguments: argparse.Namespace) -> int:
    private_key = _load_private_key(arguments.private_key)
    contribution = Contribution(
        kind=arguments.kind,
        title=arguments.title,
        body=arguments.body,
        created_at=datetime.now(UTC),
        parent=arguments.parent,
    )
    receipt = ArtifactSubmitter(
        private_key=private_key,
        cometbft_rpc_url=arguments.rpc_url,
    ).submit(contribution)
    print(
        _SubmissionOutput(
            artifact_ref=receipt.artifact_ref,
            accepted_for_broadcast=receipt.accepted,
        ).model_dump_json()
    )
    return 0 if receipt.accepted else 1


def _query(arguments: argparse.Namespace) -> int:
    if not arguments.ledger_path.is_file():
        raise FileNotFoundError(f"artifact ledger does not exist: {arguments.ledger_path}")

    snapshot = SQLiteArtifactLedgerStore(path=arguments.ledger_path).load()
    index = KnowledgeGraphIndex()
    if snapshot is not None:
        index.refresh(snapshot)

    queries = KnowledgeGraphQueries(index=index)
    artifacts = _execute_query(queries, arguments)
    print(
        _QueryOutput(
            indexed_height=queries.indexed_height,
            artifacts=tuple(_ArtifactOutput.from_indexed(artifact) for artifact in artifacts),
        ).model_dump_json()
    )
    return 0


def _execute_query(
    queries: KnowledgeGraphQueries,
    arguments: argparse.Namespace,
) -> tuple[IndexedArtifact, ...]:
    if arguments.query == "artifact":
        artifact = queries.artifact_by_ref(arguments.artifact_ref)
        if artifact is None:
            raise ValueError(f"artifact is not indexed: {arguments.artifact_ref}")
        return (artifact,)
    if arguments.query == "contributions":
        return (
            queries.contributions()
            if arguments.kind is None
            else queries.contributions_by_kind(arguments.kind)
        )
    if arguments.query == "children":
        return queries.children_by_parent_ref(arguments.parent_ref)
    if arguments.query == "relations":
        return (
            queries.relations()
            if arguments.kind is None
            else queries.relations_by_kind(arguments.kind)
        )
    if arguments.query == "outgoing-relations":
        return queries.outgoing_relations_by_ref(arguments.artifact_ref, kind=arguments.kind)
    if arguments.query == "incoming-relations":
        return queries.incoming_relations_by_ref(arguments.artifact_ref, kind=arguments.kind)
    raise RuntimeError("query command was not recognized")


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
    query = commands.add_parser(
        "query",
        help="query committed knowledge",
        description="Query committed knowledge from a local Discovery Net ledger.",
    )
    query.add_argument(
        "--ledger-path",
        required=True,
        type=Path,
        help="path to the local SQLite artifact ledger",
    )
    queries = query.add_subparsers(dest="query", required=True)

    artifact = queries.add_parser("artifact", help="get an artifact by reference")
    artifact.add_argument("artifact_ref", type=_artifact_reference)

    contributions = queries.add_parser("contributions", help="list contributions")
    contributions.add_argument(
        "--kind",
        type=ContributionKind,
        choices=tuple(ContributionKind),
        help="only return contributions of this kind",
    )

    children = queries.add_parser("children", help="list children of a parent artifact")
    children.add_argument("parent_ref", type=_artifact_reference)

    relations = queries.add_parser("relations", help="list contribution relations")
    _add_relation_kind_argument(relations)

    outgoing = queries.add_parser(
        "outgoing-relations",
        help="list relations originating from an artifact",
    )
    outgoing.add_argument("artifact_ref", type=_artifact_reference)
    _add_relation_kind_argument(outgoing)

    incoming = queries.add_parser(
        "incoming-relations",
        help="list relations terminating at an artifact",
    )
    incoming.add_argument("artifact_ref", type=_artifact_reference)
    _add_relation_kind_argument(incoming)
    return parser


def _add_relation_kind_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--kind",
        type=RelationKind,
        choices=tuple(RelationKind),
        help="only return relations of this kind",
    )


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
