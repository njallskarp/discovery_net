import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from discovery_net.entrypoints.cli import main
from discovery_net.knowledge_graph import ArtifactRef, Contribution, ContributionKind
from discovery_net.submission import ArtifactSubmitter, SubmissionReceipt

PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PARENT_REF = "bafkreiheoeszncz3oecj7pciali6ictr5ijvtxwpvowpoczulcadpvh7bq"


def test_cli_builds_and_submits_a_contribution_to_the_local_node(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: CLI arguments → contribution → submitter; guards the agent-facing boundary."""
    key_path = _write_private_key(tmp_path)
    submitter = MagicMock(spec=ArtifactSubmitter)
    submitter.submit.return_value = SubmissionReceipt(
        artifact_ref=ArtifactRef("bafy-artifact"),
        accepted=True,
    )

    with patch(
        "discovery_net.entrypoints.cli.ArtifactSubmitter",
        return_value=submitter,
    ) as submitter_type:
        exit_code = main(
            (
                "submit",
                "--private-key",
                str(key_path),
                "--kind",
                ContributionKind.PROOF_ATTEMPT,
                "--title",
                "A spectral approach",
                "--body",
                "Consider the associated operator.",
                "--parent",
                PARENT_REF,
            )
        )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "artifact_ref": "bafy-artifact",
        "accepted_for_broadcast": True,
    }
    constructor_arguments = submitter_type.call_args.kwargs
    assert constructor_arguments["cometbft_rpc_url"] == "http://127.0.0.1:26657"
    loaded_key = constructor_arguments["private_key"]
    assert isinstance(loaded_key, Ed25519PrivateKey)
    contribution = submitter.submit.call_args.args[0]
    assert isinstance(contribution, Contribution)
    assert contribution.kind is ContributionKind.PROOF_ATTEMPT
    assert contribution.title == "A spectral approach"
    assert contribution.body == "Consider the associated operator."
    assert contribution.parent == PARENT_REF
    assert contribution.created_at.utcoffset() is not None


def test_cli_returns_failure_when_check_tx_rejects_the_contribution(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path: rejected CheckTx → CLI result; guards acceptance from being reported as success."""
    key_path = _write_private_key(tmp_path)
    submitter = MagicMock(spec=ArtifactSubmitter)
    submitter.submit.return_value = SubmissionReceipt(
        artifact_ref=ArtifactRef("bafy-rejected"),
        accepted=False,
    )

    with patch("discovery_net.entrypoints.cli.ArtifactSubmitter", return_value=submitter):
        exit_code = main(
            (
                "submit",
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
    assert json.loads(capsys.readouterr().out)["accepted_for_broadcast"] is False


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
