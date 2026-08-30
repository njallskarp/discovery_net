# Provides the command-line interface to a local Discovery Net node.

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)
from pydantic import BaseModel, ConfigDict

from discovery_net.entrypoints.graphql import GraphQLQueryExecutor
from discovery_net.indexing import IndexedArtifact, KnowledgeGraphIndex
from discovery_net.knowledge_graph import (
    ArtifactRef,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.node import SQLiteApplicationStateStore
from discovery_net.node.runtime import CometBFTValidatorProvisioner, ValidatorIdentity
from discovery_net.query import KnowledgeGraphQueries
from discovery_net.submission import (
    ArtifactSubmitter,
    IncomingRelation,
    OutgoingRelation,
    SubmissionError,
    ValidatorGovernanceReceipt,
    ValidatorGovernanceSubmitter,
)
from discovery_net.wire import (
    PayloadType,
    ValidatorGovernanceTransaction,
    ValidatorMembershipOperation,
    ValidatorOperator,
    approve_validator_proposal,
    complete_validator_nomination,
    decode_consensus_validator_nomination,
    decode_validator_nomination,
    encode_consensus_validator_nomination,
    encode_validator_nomination,
    parse_artifact_ref,
    propose_validator_membership,
)

_DEFAULT_COMETBFT_RPC_URL = "http://127.0.0.1:26657"


class _SubmissionOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_refs: tuple[ArtifactRef, ...]
    transaction_hash: str
    check_tx_code: int
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
        envelope = indexed.envelope
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


class _GraphQLOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    data: dict[str, object] | None
    errors: tuple[dict[str, object], ...]


class _ValidatorNominationOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    consensus_public_key: str
    governance_public_key: str
    nomination: str


class _ValidatorSubmissionOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: str
    transaction_hash: str
    check_tx_code: int
    accepted_for_broadcast: bool


class _ValidatorOperatorOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    consensus_public_key: str
    governance_public_key: str


class _ValidatorProposalOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: str
    operation: ValidatorMembershipOperation
    operator: _ValidatorOperatorOutput
    approvals: tuple[str, ...]


class _ScheduledValidatorChangeOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: str
    operation: ValidatorMembershipOperation
    operator: _ValidatorOperatorOutput
    effective_height: int


class _ValidatorStatusOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    committed_height: int
    approval_threshold: int
    validator_power: int
    operators: tuple[_ValidatorOperatorOutput, ...]
    proposals: tuple[_ValidatorProposalOutput, ...]
    scheduled_change: _ScheduledValidatorChangeOutput | None


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one Discovery Net command and return its process exit code."""
    parsed = _argument_parser().parse_args(arguments)
    try:
        if parsed.command == "submit":
            return _submit(parsed)
        if parsed.command == "query":
            return _query(parsed)
        if parsed.command == "validator":
            return _validator(parsed)
        return _graphql(parsed)
    except (OSError, sqlite3.Error, TypeError, ValueError, SubmissionError) as error:
        _write_error(error)
        return 1


def _submit(arguments: argparse.Namespace) -> int:
    private_key = _load_private_key(arguments.private_key)
    submitter = ArtifactSubmitter(
        private_key=private_key,
        cometbft_rpc_url=arguments.rpc_url,
    )
    if arguments.submission == "contribution":
        receipt = submitter.submit_contribution(
            Contribution(
                kind=arguments.kind,
                title=arguments.title,
                body=arguments.body,
                created_at=datetime.now(UTC),
            ),
            relations=(
                *(
                    OutgoingRelation(kind=kind, to_contribution=reference)
                    for kind, reference in arguments.outgoing
                ),
                *(
                    IncomingRelation(from_contribution=reference, kind=kind)
                    for kind, reference in arguments.incoming
                ),
            ),
        )
    else:
        receipt = submitter.submit_relation(
            ContributionRelation(
                from_contribution=arguments.from_contribution,
                to_contribution=arguments.to_contribution,
                kind=arguments.kind,
                created_at=datetime.now(UTC),
            )
        )
    _write_output(
        _SubmissionOutput(
            artifact_refs=receipt.artifact_refs,
            transaction_hash=receipt.transaction_hash,
            check_tx_code=receipt.check_tx_code,
            accepted_for_broadcast=receipt.accepted,
        )
    )
    return 0 if receipt.accepted else 1


def _query(arguments: argparse.Namespace) -> int:
    queries = _load_queries(arguments.ledger_path)
    artifacts = _execute_query(queries, arguments)
    _write_output(
        _QueryOutput(
            indexed_height=queries.indexed_height,
            artifacts=tuple(_ArtifactOutput.from_indexed(artifact) for artifact in artifacts),
        )
    )
    return 0


def _graphql(arguments: argparse.Namespace) -> int:
    variables = None
    if arguments.variables is not None:
        decoded = json.loads(arguments.variables)
        if not isinstance(decoded, dict):
            raise ValueError("GraphQL variables must be a JSON object")
        variables = decoded

    execution = GraphQLQueryExecutor(queries=_load_queries(arguments.ledger_path)).execute(
        arguments.document,
        variables=variables,
        operation_name=arguments.operation_name,
    )
    _write_output(_GraphQLOutput(data=execution.data, errors=execution.errors))
    return 0 if execution.succeeded else 1


def _validator(arguments: argparse.Namespace) -> int:
    if arguments.validator_action == "nominate-consensus":
        consensus_nomination = CometBFTValidatorProvisioner().nominate_validator(
            ValidatorIdentity(directory=arguments.home),
            chain_id=arguments.chain_id,
            governance_public_key=_load_public_key(arguments.governance_public_key),
        )
        _write_new_public_file(
            arguments.output,
            encode_consensus_validator_nomination(consensus_nomination),
        )
        _write_output(
            _ValidatorNominationOutput(
                consensus_public_key=consensus_nomination.operator.consensus_public_key.hex(),
                governance_public_key=consensus_nomination.operator.governance_public_key.hex(),
                nomination=str(arguments.output),
            )
        )
        return 0

    if arguments.validator_action == "complete-nomination":
        consensus_nomination = decode_consensus_validator_nomination(
            arguments.consensus_nomination.read_bytes()
        )
        signed_nomination = complete_validator_nomination(
            nomination=consensus_nomination,
            governance_private_key=_load_private_key(arguments.governance_private_key),
        )
        _write_new_public_file(
            arguments.output,
            encode_validator_nomination(signed_nomination),
        )
        _write_output(
            _ValidatorNominationOutput(
                consensus_public_key=signed_nomination.operator.consensus_public_key.hex(),
                governance_public_key=signed_nomination.operator.governance_public_key.hex(),
                nomination=str(arguments.output),
            )
        )
        return 0

    if arguments.validator_action == "status":
        _write_output(_validator_status(arguments.ledger_path))
        return 0

    submitter = ValidatorGovernanceSubmitter(cometbft_rpc_url=arguments.rpc_url)
    governance_private_key = _load_private_key(arguments.governance_private_key)
    transaction: ValidatorGovernanceTransaction
    if arguments.validator_action == "propose-add":
        signed_nomination = decode_validator_nomination(arguments.nomination.read_bytes())
        transaction = propose_validator_membership(
            chain_id=signed_nomination.chain_id,
            operation=ValidatorMembershipOperation.ADD,
            operator=signed_nomination.operator,
            sponsor_private_key=governance_private_key,
            nomination=signed_nomination,
        )
    elif arguments.validator_action == "propose-remove":
        transaction = propose_validator_membership(
            chain_id=submitter.chain_id(),
            operation=ValidatorMembershipOperation.REMOVE,
            operator=ValidatorOperator(
                consensus_public_key=arguments.consensus_public_key,
                governance_public_key=arguments.operator_governance_public_key,
            ),
            sponsor_private_key=governance_private_key,
        )
    elif arguments.validator_action == "approve":
        transaction = approve_validator_proposal(
            chain_id=submitter.chain_id(),
            proposal_id=arguments.proposal_id,
            private_key=governance_private_key,
        )
    else:
        raise AssertionError("unknown validator action")
    receipt = submitter.submit(transaction)
    _write_validator_receipt(receipt)
    return 0 if receipt.accepted else 1


def _validator_status(ledger_path: Path) -> _ValidatorStatusOutput:
    if not ledger_path.is_file():
        raise FileNotFoundError(f"artifact ledger does not exist: {ledger_path}")
    snapshot = SQLiteApplicationStateStore(path=ledger_path).load()
    if snapshot is None or snapshot.validator_governance is None:
        raise ValueError("validator governance is not enabled in this ledger")
    state = snapshot.validator_governance
    scheduled = state.scheduled_change
    return _ValidatorStatusOutput(
        committed_height=snapshot.height,
        approval_threshold=state.approval_threshold,
        validator_power=state.validator_power,
        operators=tuple(_operator_output(value) for value in state.operators),
        proposals=tuple(
            _ValidatorProposalOutput(
                proposal_id=value.proposal_id.hex(),
                operation=value.proposal.operation,
                operator=_operator_output(value.proposal.operator),
                approvals=tuple(key.hex() for key in value.approvals),
            )
            for value in state.proposals
        ),
        scheduled_change=(
            None
            if scheduled is None
            else _ScheduledValidatorChangeOutput(
                proposal_id=scheduled.proposal_id.hex(),
                operation=scheduled.operation,
                operator=_operator_output(scheduled.operator),
                effective_height=scheduled.effective_height,
            )
        ),
    )


def _operator_output(operator: ValidatorOperator) -> _ValidatorOperatorOutput:
    return _ValidatorOperatorOutput(
        consensus_public_key=operator.consensus_public_key.hex(),
        governance_public_key=operator.governance_public_key.hex(),
    )


def _write_validator_receipt(receipt: ValidatorGovernanceReceipt) -> None:
    _write_output(
        _ValidatorSubmissionOutput(
            proposal_id=receipt.proposal_id.hex(),
            transaction_hash=receipt.transaction_hash,
            check_tx_code=receipt.check_tx_code,
            accepted_for_broadcast=receipt.accepted,
        )
    )


def _load_queries(ledger_path: Path) -> KnowledgeGraphQueries:
    if not ledger_path.is_file():
        raise FileNotFoundError(f"artifact ledger does not exist: {ledger_path}")

    snapshot = SQLiteApplicationStateStore(path=ledger_path).load_artifact_ledger()
    index = KnowledgeGraphIndex()
    if snapshot is not None:
        index.refresh(snapshot)
    return KnowledgeGraphQueries(index=index)


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
    if arguments.query == "outgoing-contributions":
        return queries.outgoing_contributions_by_ref(
            arguments.artifact_ref,
            via=arguments.via,
            kind=arguments.kind,
        )
    if arguments.query == "incoming-contributions":
        return queries.incoming_contributions_by_ref(
            arguments.artifact_ref,
            via=arguments.via,
            kind=arguments.kind,
        )
    raise RuntimeError("query command was not recognized")


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="discovery-net",
        description="Interact with a local Discovery Net node.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser(
        "submit",
        help="submit knowledge",
        description="Submit an atomic artifact transaction through a local node.",
    )
    submissions = submit.add_subparsers(dest="submission", required=True)

    contribution = submissions.add_parser(
        "contribution",
        help="submit a contribution and its initial relations",
    )
    _add_submission_arguments(contribution)
    contribution.add_argument(
        "--kind",
        required=True,
        type=ContributionKind,
        choices=tuple(ContributionKind),
        help="mathematical or organizational role of the contribution",
    )
    contribution.add_argument("--title", required=True, help="short contribution title")
    contribution.add_argument("--body", required=True, help="contribution body")
    contribution.add_argument(
        "--outgoing",
        action="append",
        default=[],
        type=_relation_argument,
        metavar="KIND:CONTRIBUTION_REF",
        help="initial relation from this contribution; may be repeated",
    )
    contribution.add_argument(
        "--incoming",
        action="append",
        default=[],
        type=_relation_argument,
        metavar="KIND:CONTRIBUTION_REF",
        help="initial relation to this contribution; may be repeated",
    )

    relation = submissions.add_parser(
        "relation",
        help="submit a relation between existing contributions",
    )
    _add_submission_arguments(relation)
    relation.add_argument(
        "--kind",
        required=True,
        type=RelationKind,
        choices=tuple(RelationKind),
        help="claimed relationship between the contributions",
    )
    relation.add_argument(
        "--from",
        dest="from_contribution",
        required=True,
        type=_artifact_reference,
        help="source contribution reference",
    )
    relation.add_argument(
        "--to",
        dest="to_contribution",
        required=True,
        type=_artifact_reference,
        help="destination contribution reference",
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

    outgoing_contributions = queries.add_parser(
        "outgoing-contributions",
        help="list contributions reached through outgoing relations",
    )
    _add_contribution_traversal_arguments(outgoing_contributions)

    incoming_contributions = queries.add_parser(
        "incoming-contributions",
        help="list contributions reached through incoming relations",
    )
    _add_contribution_traversal_arguments(incoming_contributions)

    graphql = commands.add_parser(
        "graphql",
        help="execute a GraphQL query",
        description="Execute GraphQL against committed knowledge in a local ledger.",
    )
    graphql.add_argument(
        "--ledger-path",
        required=True,
        type=Path,
        help="path to the local SQLite artifact ledger",
    )
    graphql.add_argument(
        "--variables",
        help="GraphQL variables as a JSON object",
    )
    graphql.add_argument(
        "--operation-name",
        help="operation to execute when the document contains multiple operations",
    )
    graphql.add_argument("document", help="GraphQL query document")

    validator = commands.add_parser(
        "validator",
        help="nominate, approve, and inspect validator membership",
    )
    validator_actions = validator.add_subparsers(dest="validator_action", required=True)

    nominate_consensus = validator_actions.add_parser(
        "nominate-consensus",
        help="sign a candidate nomination without importing its governance private key",
    )
    nominate_consensus.add_argument("--home", required=True, type=Path)
    nominate_consensus.add_argument("--chain-id", required=True)
    nominate_consensus.add_argument("--governance-public-key", required=True, type=Path)
    nominate_consensus.add_argument("--output", required=True, type=Path)

    complete_nomination = validator_actions.add_parser(
        "complete-nomination",
        help="add the offline governance signature to a consensus-signed nomination",
    )
    complete_nomination.add_argument("--consensus-nomination", required=True, type=Path)
    complete_nomination.add_argument("--governance-private-key", required=True, type=Path)
    complete_nomination.add_argument("--output", required=True, type=Path)

    propose_add = validator_actions.add_parser(
        "propose-add",
        help="sponsor a candidate nomination as the first approval",
    )
    propose_add.add_argument("--nomination", required=True, type=Path)
    _add_governance_submission_arguments(propose_add)

    propose_remove = validator_actions.add_parser(
        "propose-remove",
        help="sponsor removal of one exact validator operator",
    )
    propose_remove.add_argument("--consensus-public-key", required=True, type=_raw_public_key)
    propose_remove.add_argument(
        "--operator-governance-public-key",
        required=True,
        type=_raw_public_key,
    )
    _add_governance_submission_arguments(propose_remove)

    approve = validator_actions.add_parser(
        "approve",
        help="approve a committed validator-membership proposal",
    )
    approve.add_argument("proposal_id", type=_proposal_id)
    _add_governance_submission_arguments(approve)

    validator_status = validator_actions.add_parser(
        "status",
        help="show committed validator-governance state",
    )
    validator_status.add_argument("--ledger-path", required=True, type=Path)
    return parser


def _add_submission_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--private-key",
        required=True,
        type=Path,
        help="path to an unencrypted Ed25519 PEM private key",
    )
    parser.add_argument(
        "--rpc-url",
        default=_DEFAULT_COMETBFT_RPC_URL,
        help=f"local CometBFT RPC URL (default: {_DEFAULT_COMETBFT_RPC_URL})",
    )


def _add_governance_submission_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--governance-private-key", required=True, type=Path)
    parser.add_argument(
        "--rpc-url",
        default=_DEFAULT_COMETBFT_RPC_URL,
        help=f"CometBFT RPC URL (default: {_DEFAULT_COMETBFT_RPC_URL})",
    )


def _add_relation_kind_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--kind",
        type=RelationKind,
        choices=tuple(RelationKind),
        help="only return relations of this kind",
    )


def _add_contribution_traversal_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("artifact_ref", type=_artifact_reference)
    parser.add_argument(
        "--via",
        required=True,
        type=RelationKind,
        choices=tuple(RelationKind),
        help="relation kind to follow",
    )
    parser.add_argument(
        "--kind",
        type=ContributionKind,
        choices=tuple(ContributionKind),
        help="only return contributions of this kind",
    )


def _write_output(output: BaseModel) -> None:
    sys.stdout.write(f"{output.model_dump_json()}\n")


def _write_error(error: Exception) -> None:
    sys.stderr.write(f"error: {error}\n")


def _artifact_reference(value: str) -> ArtifactRef:
    try:
        return parse_artifact_ref(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _relation_argument(value: str) -> tuple[RelationKind, ArtifactRef]:
    kind_value, separator, reference_value = value.partition(":")
    if not separator:
        raise argparse.ArgumentTypeError("relation must use KIND:CONTRIBUTION_REF")
    try:
        return RelationKind(kind_value), parse_artifact_ref(reference_value)
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


def _load_public_key(path: Path) -> bytes:
    try:
        public_key = load_pem_public_key(path.read_bytes())
    except (TypeError, ValueError) as error:
        raise ValueError("public key file must contain an Ed25519 PEM public key") from error
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("public key file must contain an Ed25519 public key")
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _raw_public_key(value: str) -> bytes:
    return _fixed_hex(value, byte_length=32, description="public key")


def _proposal_id(value: str) -> bytes:
    return _fixed_hex(value, byte_length=32, description="proposal ID")


def _fixed_hex(value: str, *, byte_length: int, description: str) -> bytes:
    try:
        decoded = bytes.fromhex(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{description} must be hexadecimal") from error
    if len(decoded) != byte_length or value.lower() != decoded.hex():
        raise argparse.ArgumentTypeError(
            f"{description} must be {byte_length * 2} hexadecimal characters"
        )
    return decoded


def _write_new_public_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as output:
            output.write(content)
    except FileExistsError:
        raise FileExistsError(f"output already exists: {path}") from None


if __name__ == "__main__":
    raise SystemExit(main())
