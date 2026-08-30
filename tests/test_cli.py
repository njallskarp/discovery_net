import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from discovery_net.entrypoints.cli import main
from discovery_net.knowledge_graph import (
    Artifact,
    ArtifactRef,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.node import (
    ArtifactLedgerEntry,
    ArtifactLedgerSnapshot,
    SQLiteApplicationStateStore,
)
from discovery_net.submission import (
    ArtifactSubmitter,
    IncomingRelation,
    OutgoingRelation,
    SubmissionReceipt,
    ValidatorGovernanceReceipt,
    ValidatorGovernanceSubmitter,
)
from discovery_net.wire import (
    ValidatorMembershipProposal,
    artifact_ref,
    decode_validator_nomination,
    sign_artifact,
    sign_transaction,
    verify_validator_nomination,
)
from tests.runtime_test_support import write_validator_identity

PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
TRANSACTION_HASH = "A" * 64
PARENT_REF = ArtifactRef("bafkreiheoeszncz3oecj7pciali6ictr5ijvtxwpvowpoczulcadpvh7bq")
OTHER_REF = ArtifactRef("bafkreickvwi5x3dzjh5ap7qa5onmiusawgdigfdufxph4v5ubzgku2aymm")


def test_cli_builds_and_submits_a_contribution_to_the_local_node(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: CLI arguments → contribution → submitter; guards the agent-facing boundary."""
    key_path = _write_private_key(tmp_path)
    submitter = MagicMock(spec=ArtifactSubmitter)
    submitter.submit_contribution.return_value = SubmissionReceipt(
        artifact_refs=(ArtifactRef("bafy-artifact"),),
        transaction_hash=TRANSACTION_HASH,
        check_tx_code=0,
    )

    with patch(
        "discovery_net.entrypoints.cli.ArtifactSubmitter",
        return_value=submitter,
    ) as submitter_type:
        exit_code = main(
            (
                "submit",
                "contribution",
                "--private-key",
                str(key_path),
                "--kind",
                ContributionKind.PROOF_ATTEMPT,
                "--title",
                "A spectral approach",
                "--body",
                "Consider the associated operator.",
                "--outgoing",
                f"about:{PARENT_REF}",
                "--incoming",
                f"cites:{PARENT_REF}",
            )
        )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.endswith("\n")
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "artifact_refs": ["bafy-artifact"],
        "transaction_hash": TRANSACTION_HASH,
        "check_tx_code": 0,
        "accepted_for_broadcast": True,
    }
    constructor_arguments = submitter_type.call_args.kwargs
    assert constructor_arguments["cometbft_rpc_url"] == "http://127.0.0.1:26657"
    loaded_key = constructor_arguments["private_key"]
    assert isinstance(loaded_key, Ed25519PrivateKey)
    contribution = submitter.submit_contribution.call_args.args[0]
    assert isinstance(contribution, Contribution)
    assert contribution.kind is ContributionKind.PROOF_ATTEMPT
    assert contribution.title == "A spectral approach"
    assert contribution.body == "Consider the associated operator."
    assert contribution.created_at.utcoffset() is not None
    assert submitter.submit_contribution.call_args.kwargs["relations"] == (
        OutgoingRelation(kind=RelationKind.ABOUT, to_contribution=PARENT_REF),
        IncomingRelation(from_contribution=PARENT_REF, kind=RelationKind.CITES),
    )


def test_cli_returns_failure_when_check_tx_rejects_the_contribution(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: rejected CheckTx → CLI result; guards acceptance from being reported as success."""
    key_path = _write_private_key(tmp_path)
    submitter = MagicMock(spec=ArtifactSubmitter)
    submitter.submit_contribution.return_value = SubmissionReceipt(
        artifact_refs=(ArtifactRef("bafy-rejected"),),
        transaction_hash=TRANSACTION_HASH,
        check_tx_code=2,
    )

    with patch("discovery_net.entrypoints.cli.ArtifactSubmitter", return_value=submitter):
        exit_code = main(
            (
                "submit",
                "contribution",
                "--private-key",
                str(key_path),
                "--kind",
                ContributionKind.OBJECTION,
                "--title",
                "A rejected objection",
                "--body",
                "This should not be reported as accepted.",
            )
        )

    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["transaction_hash"] == TRANSACTION_HASH
    assert output["check_tx_code"] == 2
    assert output["accepted_for_broadcast"] is False


def test_cli_submits_a_post_hoc_relation_between_existing_contributions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: relation arguments → relation artifact; guards the post-hoc connection workflow."""
    key_path = _write_private_key(tmp_path)
    submitter = MagicMock(spec=ArtifactSubmitter)
    submitter.submit_relation.return_value = SubmissionReceipt(
        artifact_refs=(ArtifactRef("bafy-relation"),),
        transaction_hash=TRANSACTION_HASH,
        check_tx_code=0,
    )

    with patch("discovery_net.entrypoints.cli.ArtifactSubmitter", return_value=submitter):
        exit_code = main(
            (
                "submit",
                "relation",
                "--private-key",
                str(key_path),
                "--kind",
                RelationKind.CITES,
                "--from",
                PARENT_REF,
                "--to",
                OTHER_REF,
            )
        )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["artifact_refs"] == ["bafy-relation"]
    relation = submitter.submit_relation.call_args.args[0]
    assert isinstance(relation, ContributionRelation)
    assert relation.from_contribution == PARENT_REF
    assert relation.to_contribution == OTHER_REF
    assert relation.kind is RelationKind.CITES


def test_cli_reports_an_invalid_private_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: invalid local identity → CLI error; guards unsigned input from reaching the node."""
    key_path = tmp_path / "agent.pem"
    key_path.write_text("not a private key")

    exit_code = main(
        (
            "submit",
            "contribution",
            "--private-key",
            str(key_path),
            "--kind",
            ContributionKind.FINDING,
            "--title",
            "A finding",
            "--body",
            "A body.",
        )
    )

    assert exit_code == 1
    assert "must contain an unencrypted Ed25519 PEM private key" in capsys.readouterr().err


def test_cli_returns_a_committed_artifact_with_its_provenance(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: SQLite snapshot → index → query facade → JSON; guards complete artifact output."""
    ledger_path, references = _write_ledger(tmp_path)

    output = _run_query(
        ledger_path,
        capsys,
        "artifact",
        references["problem"],
    )

    assert output["indexed_height"] == 1
    artifact = cast(list[dict[str, object]], output["artifacts"])[0]
    assert artifact["artifact_ref"] == references["problem"]
    assert artifact["payload_type"] == "contribution"
    assert artifact["artifact"] == {
        "kind": "problem_statement",
        "title": "A problem",
        "body": "Body for A problem",
        "created_at": "2026-08-26T16:00:00Z",
    }
    assert artifact["chain_id"] == "discovery-net-devnet"
    assert artifact["signer_public_key"] == PRIVATE_KEY.public_key().public_bytes_raw().hex()
    assert len(cast(str, artifact["signature"])) == 128
    assert artifact["height"] == 1
    assert artifact["transaction_index"] == 1


def test_cli_maps_explicit_query_commands_to_the_knowledge_graph(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: query commands → graph operations; guards selection and traversal semantics."""
    ledger_path, references = _write_ledger(tmp_path)

    assert _output_refs(_run_query(ledger_path, capsys, "contributions")) == (
        references["area"],
        references["problem"],
        references["finding"],
    )
    assert _output_refs(_run_query(ledger_path, capsys, "contributions", "--kind", "finding")) == (
        references["finding"],
    )
    assert _output_refs(_run_query(ledger_path, capsys, "relations")) == (references["relation"],)
    assert _output_refs(_run_query(ledger_path, capsys, "relations", "--kind", "supports")) == (
        references["relation"],
    )
    assert _output_refs(
        _run_query(ledger_path, capsys, "outgoing-relations", references["finding"])
    ) == (references["relation"],)
    assert _output_refs(
        _run_query(ledger_path, capsys, "incoming-relations", references["problem"])
    ) == (references["relation"],)
    assert _output_refs(
        _run_query(
            ledger_path,
            capsys,
            "outgoing-contributions",
            references["finding"],
            "--via",
            "supports",
        )
    ) == (references["problem"],)
    assert _output_refs(
        _run_query(
            ledger_path,
            capsys,
            "incoming-contributions",
            references["problem"],
            "--via",
            "supports",
        )
    ) == (references["finding"],)
    assert (
        _output_refs(
            _run_query(
                ledger_path,
                capsys,
                "outgoing-contributions",
                references["finding"],
                "--via",
                "supports",
                "--kind",
                "question",
            )
        )
        == ()
    )
    assert (
        _output_refs(
            _run_query(
                ledger_path,
                capsys,
                "outgoing-relations",
                references["finding"],
                "--kind",
                "about",
            )
        )
        == ()
    )


def test_cli_query_rejects_missing_local_data(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: absent ledger or artifact → CLI error; guards reads from inventing local state."""
    missing_ledger = tmp_path / "missing.sqlite"

    assert main(("query", "--ledger-path", str(missing_ledger), "contributions")) == 1
    assert "artifact ledger does not exist" in capsys.readouterr().err
    assert not missing_ledger.exists()

    ledger_path, _ = _write_ledger(tmp_path)
    assert main(("query", "--ledger-path", str(ledger_path), "artifact", PARENT_REF)) == 1
    assert "artifact is not indexed" in capsys.readouterr().err


def test_cli_executes_graphql_with_variables_against_the_local_ledger(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: GraphQL document → local snapshot → nested JSON; guards the agent query boundary."""
    ledger_path, references = _write_ledger(tmp_path)

    exit_code = main(
        (
            "graphql",
            "--ledger-path",
            str(ledger_path),
            "--variables",
            json.dumps({"kind": "FINDING"}),
            """
            query Findings($kind: ContributionKind!) {
              indexedHeight
              contributions(kind: $kind) {
                artifactRef
                title
                supported: outgoingContributions(via: SUPPORTS) { artifactRef title }
              }
            }
            """,
        )
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "data": {
            "indexedHeight": "1",
            "contributions": [
                {
                    "artifactRef": references["finding"],
                    "title": "A finding",
                    "supported": [
                        {
                            "artifactRef": references["problem"],
                            "title": "A problem",
                        }
                    ],
                }
            ],
        },
        "errors": [],
    }


def test_cli_returns_failure_with_a_structured_graphql_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: invalid GraphQL document → formatted response; guards errors from becoming crashes."""
    ledger_path, _ = _write_ledger(tmp_path)

    exit_code = main(
        (
            "graphql",
            "--ledger-path",
            str(ledger_path),
            "{ unknownField }",
        )
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == ""
    output = cast(dict[str, object], json.loads(captured.out))
    assert output["data"] is None
    errors = cast(list[dict[str, object]], output["errors"])
    assert errors[0]["message"] == "Cannot query field 'unknownField' on type 'Query'."


def test_cli_keeps_candidate_keys_separate_and_submits_a_sponsored_nomination(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "candidate"
    write_validator_identity(home, seed_byte=71)
    governance_key = Ed25519PrivateKey.from_private_bytes(bytes([72]) * 32)
    governance_private_path = tmp_path / "governance.pem"
    governance_private_path.write_bytes(
        governance_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    governance_public_path = tmp_path / "governance.pub.pem"
    governance_public_path.write_bytes(
        governance_key.public_key().public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        )
    )
    consensus_nomination = tmp_path / "consensus-nomination.json"
    nomination = tmp_path / "nomination.json"

    assert (
        main(
            (
                "validator",
                "nominate-consensus",
                "--home",
                str(home),
                "--chain-id",
                "discovery-1",
                "--governance-public-key",
                str(governance_public_path),
                "--output",
                str(consensus_nomination),
            )
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            (
                "validator",
                "complete-nomination",
                "--consensus-nomination",
                str(consensus_nomination),
                "--governance-private-key",
                str(governance_private_path),
                "--output",
                str(nomination),
            )
        )
        == 0
    )
    completed = decode_validator_nomination(nomination.read_bytes())
    assert verify_validator_nomination(completed)
    capsys.readouterr()

    submitter = MagicMock(spec=ValidatorGovernanceSubmitter)
    submitter.submit.return_value = ValidatorGovernanceReceipt(
        proposal_id=bytes([73]) * 32,
        transaction_hash=TRANSACTION_HASH,
        check_tx_code=0,
    )
    with patch(
        "discovery_net.entrypoints.cli.ValidatorGovernanceSubmitter",
        return_value=submitter,
    ):
        exit_code = main(
            (
                "validator",
                "propose-add",
                "--nomination",
                str(nomination),
                "--governance-private-key",
                str(governance_private_path),
            )
        )

    assert exit_code == 0
    proposal = submitter.submit.call_args.args[0]
    assert isinstance(proposal, ValidatorMembershipProposal)
    assert proposal.nomination == completed
    assert json.loads(capsys.readouterr().out) == {
        "proposal_id": (bytes([73]) * 32).hex(),
        "transaction_hash": TRANSACTION_HASH,
        "check_tx_code": 0,
        "accepted_for_broadcast": True,
    }


def _write_private_key(directory: Path) -> Path:
    path = directory / "agent.pem"
    path.write_bytes(
        PRIVATE_KEY.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption(),
        )
    )
    return path


def _write_ledger(directory: Path) -> tuple[Path, dict[str, ArtifactRef]]:
    artifacts: list[Artifact] = [
        Contribution(
            kind=ContributionKind.MATHEMATICAL_AREA,
            title="Number theory",
            body="Body for Number theory",
            created_at=datetime(2026, 8, 26, 16, tzinfo=UTC),
        ),
        Contribution(
            kind=ContributionKind.PROBLEM_STATEMENT,
            title="A problem",
            body="Body for A problem",
            created_at=datetime(2026, 8, 26, 16, tzinfo=UTC),
        ),
    ]
    entries = [
        _ledger_entry(artifact, transaction_index=index) for index, artifact in enumerate(artifacts)
    ]
    area_ref, problem_ref = (artifact_ref(entry.transaction.envelopes[0]) for entry in entries)
    finding_entry = _ledger_entry(
        Contribution(
            kind=ContributionKind.FINDING,
            title="A finding",
            body="Body for A finding",
            created_at=datetime(2026, 8, 26, 16, tzinfo=UTC),
        ),
        transaction_index=2,
    )
    finding_ref = artifact_ref(finding_entry.transaction.envelopes[0])
    relation_entry = _ledger_entry(
        ContributionRelation(
            from_contribution=finding_ref,
            to_contribution=problem_ref,
            kind=RelationKind.SUPPORTS,
            created_at=datetime(2026, 8, 26, 16, tzinfo=UTC),
        ),
        transaction_index=3,
    )
    ledger_path = directory / "ledger.sqlite"
    SQLiteApplicationStateStore(path=ledger_path).save_artifact_ledger(
        ArtifactLedgerSnapshot(
            height=1,
            entries=(*entries, finding_entry, relation_entry),
        )
    )
    return ledger_path, {
        "area": area_ref,
        "problem": problem_ref,
        "finding": finding_ref,
        "relation": artifact_ref(relation_entry.transaction.envelopes[0]),
    }


def _ledger_entry(artifact: Artifact, *, transaction_index: int) -> ArtifactLedgerEntry:
    envelope = sign_artifact(
        chain_id="discovery-net-devnet",
        artifact=artifact,
        private_key=PRIVATE_KEY,
    )
    return ArtifactLedgerEntry(
        transaction=sign_transaction(envelopes=(envelope,), private_key=PRIVATE_KEY),
        height=1,
        transaction_index=transaction_index,
    )


def _run_query(
    ledger_path: Path,
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> dict[str, object]:
    exit_code = main(("query", "--ledger-path", str(ledger_path), *arguments))
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.endswith("\n")
    assert captured.err == ""
    return cast(dict[str, object], json.loads(captured.out))


def _output_refs(output: dict[str, object]) -> tuple[ArtifactRef, ...]:
    artifacts = cast(list[dict[str, object]], output["artifacts"])
    return tuple(ArtifactRef(cast(str, artifact["artifact_ref"])) for artifact in artifacts)
