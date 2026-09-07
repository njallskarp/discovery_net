"""Validator-authorized withdrawal through real consensus, replication, and restart."""

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from discovery_net.artifacts.edge_revocation import EdgeRevocation
from discovery_net.domains.math import Contribution, ContributionKind, RelationKind
from discovery_net.entrypoints.cli import main as cli
from discovery_net.indexing import KnowledgeGraphIndex
from discovery_net.node import LocalArtifactLedger, TransactionCode
from discovery_net.submission import ArtifactSubmitter, OutgoingRelation
from tests.integration._integration_network import IntegrationNetwork


def test_validator_revocation_converges_on_validator_and_nonvoter(
    cometbft_binary: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with IntegrationNetwork.testnet(
        binary=cometbft_binary, root=tmp_path, validators=1, non_validators=1
    ) as network:
        for node in network.nodes:
            node.start_application(with_genesis_authority=True)
        network.start_all_cometbft()
        author = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        client = ArtifactSubmitter(private_key=author, cometbft_rpc_url=network.nodes[1].rpc_url)
        area = client.submit_contribution(
            Contribution(
                kind=ContributionKind.MATHEMATICAL_AREA,
                title="Area",
                body="",
                created_at=datetime.now(UTC),
            )
        ).artifact_refs[0]
        network.wait_for_convergence(minimum_entries=1)
        problem, edge = client.submit_contribution(
            Contribution(
                kind=ContributionKind.PROBLEM_STATEMENT,
                title="Problem",
                body="",
                created_at=datetime.now(UTC),
            ),
            relations=(OutgoingRelation(kind=RelationKind.ABOUT, to_contribution=area),),
        ).artifact_refs
        before = network.wait_for_convergence(minimum_entries=2)
        denied = client.submit_revocation(
            EdgeRevocation(
                target=edge, reason="Creator has no voting power", created_at=datetime.now(UTC)
            )
        )
        assert denied.check_tx_code == TransactionCode.UNAUTHORIZED_REVOCATION
        # This identity is generated for this disposable test network, never an operator key.
        identity = json.loads(
            (network.validators[0].home / "config" / "priv_validator_key.json").read_bytes()
        )
        validator_key = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(identity["priv_key"]["value"])[:32]
        )
        key_path = tmp_path / "validator-test.pem"
        key_path.write_bytes(
            validator_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        )
        key_path.chmod(0o600)
        assert (
            cli(
                (
                    "submit",
                    "revocation",
                    "--private-key",
                    str(key_path),
                    "--rpc-url",
                    network.nodes[1].rpc_url,
                    "--target",
                    str(edge),
                    "--reason",
                    "Correct area placement",
                )
            )
            == 0
        )
        output = json.loads(capsys.readouterr().out)
        assert output["accepted_for_broadcast"]
        after = network.wait_for_convergence(minimum_entries=3)
        for previous, snapshot in zip(before, after, strict=True):
            index = KnowledgeGraphIndex()
            index.refresh(previous)
            index.append(entries=snapshot.entries[len(previous.entries) :], height=snapshot.height)
            assert len(index.contributions()) == 2
            assert index.relations() == ()
            assert index.get(problem) is not None and index.get(edge) is not None
            assert len(index.revocations(edge)) == 1
            assert LocalArtifactLedger(entries=snapshot.entries).state_hash() == network.nodes[
                0
            ].rpc.block_app_hash(height=snapshot.height)
        network.stop_all()
        for node in network.nodes:
            node.start_application(with_genesis_authority=True)
        network.start_all_cometbft()
        restored = network.wait_for_convergence(minimum_entries=3)
        assert [snapshot.entries for snapshot in restored] == [
            snapshot.entries for snapshot in after
        ]
