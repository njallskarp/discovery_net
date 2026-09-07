"""EdgeRevocation authority, atomic execution, replay, and canonical graph visibility."""

import base64
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.artifacts import ArtifactRef
from discovery_net.artifacts.edge_revocation import EdgeRevocation
from discovery_net.artifacts.encoding import canonical_json
from discovery_net.domains.math import (
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.entrypoints.cli import main as cli
from discovery_net.entrypoints.graphql import GraphQLQueryExecutor
from discovery_net.indexing import KnowledgeGraphIndex
from discovery_net.node import (
    ArtifactLedgerEntry,
    ArtifactLedgerSnapshot,
    CometBFTCallbackHandler,
    LocalArtifactLedger,
    SQLiteArtifactLedgerStore,
    TransactionCode,
    TransactionValidator,
)
from discovery_net.node.authorization import can_revoke
from discovery_net.node.genesis_authority import load_voting_power
from discovery_net.query import KnowledgeGraphQueries
from discovery_net.snapshots.ledger_baseline import export_baseline
from discovery_net.wire import (
    PayloadType,
    SignedTransaction,
    artifact_ref,
    decode_payload,
    decode_transaction,
    encode_envelope,
    encode_transaction,
    sign_artifact,
    sign_transaction,
    verify_transaction,
)
from discovery_net.wire.payload import Artifact

CHAIN = "revocation-tests"
NOW = datetime(2026, 9, 7, tzinfo=UTC)
VALIDATOR = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
AUTHOR = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
VALIDATOR_KEY = VALIDATOR.public_key().public_bytes_raw()
AUTHOR_KEY = AUTHOR.public_key().public_bytes_raw()


def transaction(
    *artifacts: Artifact, key: Ed25519PrivateKey = AUTHOR, chain: str = CHAIN
) -> SignedTransaction:
    return sign_transaction(
        envelopes=tuple(
            sign_artifact(chain_id=chain, artifact=a, private_key=key) for a in artifacts
        ),
        private_key=key,
    )


def entry(tx: SignedTransaction, height: int) -> ArtifactLedgerEntry:
    return ArtifactLedgerEntry(transaction=tx, height=height, transaction_index=0)


def fixture() -> tuple[ArtifactLedgerSnapshot, ArtifactRef, ArtifactRef, ArtifactRef]:
    source = Contribution(
        kind=ContributionKind.PROBLEM_STATEMENT, title="Problem", body="", created_at=NOW
    )
    target = Contribution(
        kind=ContributionKind.MATHEMATICAL_AREA, title="Area", body="", created_at=NOW
    )
    nodes = transaction(source, target)
    a, b = (artifact_ref(e) for e in nodes.envelopes)
    relation = transaction(
        ContributionRelation(
            kind=RelationKind.ABOUT, from_contribution=a, to_contribution=b, created_at=NOW
        )
    )
    return (
        ArtifactLedgerSnapshot(height=2, entries=(entry(nodes, 1), entry(relation, 2))),
        a,
        b,
        artifact_ref(relation.envelopes[0]),
    )


def validator(power: int = 1) -> TransactionValidator:
    return TransactionValidator(expected_chain_id=CHAIN, voting_power={VALIDATOR_KEY: power})


def revoke(target: ArtifactRef) -> EdgeRevocation:
    return EdgeRevocation(target=target, reason="Correct area placement", created_at=NOW)


def write_genesis(path: Path) -> str:
    path.write_text(
        json.dumps(
            {
                "chain_id": CHAIN,
                "validators": [
                    {
                        "pub_key": {
                            "type": "tendermint/PubKeyEd25519",
                            "value": base64.b64encode(VALIDATOR_KEY).decode(),
                        },
                        "power": "1",
                    }
                ],
            }
        )
    )
    return sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "powers,allowed",
    [
        ({}, False),
        ({AUTHOR_KEY: 10}, False),
        ({VALIDATOR_KEY: 0}, False),
        ({VALIDATOR_KEY: 1}, True),
        ({VALIDATOR_KEY: 100}, True),
    ],
)
def test_permission_is_positive_voting_power(powers: dict[bytes, int], allowed: bool) -> None:
    assert can_revoke(signer_public_key=VALIDATOR_KEY, voting_power=powers) is allowed


def test_authority_is_immutable_and_never_inferred_from_authorship() -> None:
    snapshot, _, _, edge = fixture()
    powers = {VALIDATOR_KEY: 1}
    policy = TransactionValidator(expected_chain_id=CHAIN, voting_power=powers)
    powers[AUTHOR_KEY] = 100
    result = policy.validate(
        encode_transaction(transaction(revoke(edge))),
        LocalArtifactLedger(entries=snapshot.entries),
    )
    assert result.code is TransactionCode.UNAUTHORIZED_REVOCATION
    assert AUTHOR_KEY not in policy.voting_power


@pytest.mark.parametrize("power", [-1, True, "1", 2**63])
def test_invalid_power_is_rejected_at_the_configuration_boundary(power: object) -> None:
    with pytest.raises(ValueError, match="voting power"):
        TransactionValidator(
            expected_chain_id=CHAIN, voting_power={VALIDATOR_KEY: cast(int, power)}
        )


def test_wire_is_typed_canonical_and_signed() -> None:
    _, _, _, edge = fixture()
    tx = transaction(revoke(edge), key=VALIDATOR)
    envelope = tx.envelopes[0]
    assert envelope.payload_type is PayloadType.EDGE_REVOCATION
    assert envelope.payload == canonical_json(
        {"target": edge, "reason": "Correct area placement", "created_at": "2026-09-07T00:00:00Z"}
    )
    assert decode_payload(envelope.payload_type, envelope.payload) == revoke(edge)
    assert decode_transaction(encode_transaction(tx)) == tx
    assert verify_transaction(tx)
    for payload in (
        {
            "target": edge,
            "reason": "Audit",
            "created_at": "2026-09-07T00:00:00Z",
            "is_validator": True,
        },
        {
            "target": edge,
            "reason": "Audit",
            "created_at": "2026-09-07T00:00:00Z",
            "active": True,
        },
        {"target": "not-a-cid", "reason": "Audit", "created_at": "2026-09-07T00:00:00Z"},
        {"target": edge, "reason": "Audit", "created_at": "2026-09-07T00:00:00"},
        {"target": edge, "reason": 1, "created_at": "2026-09-07T00:00:00Z"},
    ):
        with pytest.raises(ValueError):
            decode_payload(PayloadType.EDGE_REVOCATION, canonical_json(payload))
    with pytest.raises(ValueError, match="canonical"):
        decode_payload(PayloadType.EDGE_REVOCATION, envelope.payload + b" ")


def test_signature_and_chain_checks_precede_authority() -> None:
    snapshot, _, _, edge = fixture()
    ledger = LocalArtifactLedger(entries=snapshot.entries)
    tx = transaction(revoke(edge), key=VALIDATOR)
    forged = replace(tx, signature=bytes(64))
    assert (
        validator().validate(encode_transaction(forged), ledger).code
        is TransactionCode.INVALID_SIGNATURE
    )
    changed = replace(
        tx.envelopes[0],
        payload=transaction(
            EdgeRevocation(target=edge, reason="Forged reason", created_at=NOW), key=VALIDATOR
        )
        .envelopes[0]
        .payload,
    )
    forged_envelope = sign_transaction(envelopes=(changed,), private_key=VALIDATOR)
    assert (
        validator().validate(encode_transaction(forged_envelope), ledger).code
        is TransactionCode.INVALID_SIGNATURE
    )
    other_chain = transaction(revoke(edge), key=VALIDATOR, chain="elsewhere")
    assert (
        validator().validate(encode_transaction(other_chain), ledger).code
        is TransactionCode.WRONG_CHAIN
    )
    assert (
        validator(0).validate(encode_transaction(tx), ledger).code
        is TransactionCode.UNAUTHORIZED_REVOCATION
    )
    assert (
        TransactionValidator(expected_chain_id=CHAIN).validate(encode_transaction(tx), ledger).code
        is TransactionCode.UNAUTHORIZED_REVOCATION
    )


def test_target_must_exist_and_cannot_be_a_revocation() -> None:
    snapshot, _, _, edge = fixture()
    ledger = LocalArtifactLedger(entries=snapshot.entries)
    tx = transaction(revoke(edge), key=VALIDATOR)
    assert (
        validator().validate(encode_transaction(tx), LocalArtifactLedger()).code
        is TransactionCode.MISSING_REFERENCE
    )
    record = entry(tx, 3)
    ledger, _ = ledger.append_transaction(record)
    recursion = transaction(revoke(artifact_ref(tx.envelopes[0])), key=VALIDATOR)
    assert (
        validator().validate(encode_transaction(recursion), ledger).code
        is TransactionCode.INVALID_REVOCATION_TARGET
    )
    assert validator().validate(encode_transaction(tx), ledger).code is TransactionCode.DUPLICATE
    # A different signed reason is an independent audit record; its effect is idempotent.
    again = transaction(
        EdgeRevocation(target=edge, reason="Independent record", created_at=NOW), key=VALIDATOR
    )
    assert validator().validate(encode_transaction(again), ledger).code is TransactionCode.ACCEPTED


@pytest.mark.parametrize("kind", tuple(ContributionKind))
def test_even_a_validator_cannot_revoke_a_contribution(
    tmp_path: Path, kind: ContributionKind
) -> None:
    node = transaction(Contribution(kind=kind, title="Research", body="", created_at=NOW))
    snapshot = ArtifactLedgerSnapshot(height=1, entries=(entry(node, 1),))
    store = SQLiteArtifactLedgerStore(path=tmp_path / "ledger.sqlite")
    store.save(snapshot)
    handler = CometBFTCallbackHandler(validator=validator(), store=store)
    tx = encode_transaction(transaction(revoke(artifact_ref(node.envelopes[0])), key=VALIDATOR))
    before = handler.committed_head()
    assert handler.check_tx(tx).code is TransactionCode.INVALID_REVOCATION_TARGET
    result = handler.finalize_block(height=2, transactions=(tx,))
    assert result.transaction_results[0].code is TransactionCode.INVALID_REVOCATION_TARGET
    assert result.state_hash == before.state_hash
    assert handler.commit() == ()
    saved = store.load()
    assert saved is not None and saved.entries == snapshot.entries


@pytest.mark.parametrize("reason", ["", " ", "\n\t"])
def test_revocation_requires_a_public_reason(reason: str) -> None:
    _, _, _, edge = fixture()
    with pytest.raises(ValueError, match="reason must not be blank"):
        EdgeRevocation(target=edge, reason=reason, created_at=NOW)


def test_commit_restart_and_queries_preserve_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot, source, target, relation = fixture()
    store = SQLiteArtifactLedgerStore(path=tmp_path / "ledger.sqlite")
    store.save(snapshot)
    handler = CometBFTCallbackHandler(validator=validator(), store=store)
    index = KnowledgeGraphIndex()
    index.refresh(snapshot)
    original = index.get(source)
    original_edge = index.get(relation)
    assert original_edge is not None
    original_bytes = encode_envelope(original_edge.envelope)
    tx = transaction(revoke(relation), key=VALIDATOR)
    before = handler.committed_head()
    assert handler.check_tx(encode_transaction(tx)).code is TransactionCode.ACCEPTED
    assert handler.committed_head() == before
    result = handler.finalize_block(height=3, transactions=(encode_transaction(tx),))
    assert result.transaction_results[0].code is TransactionCode.ACCEPTED
    assert handler.committed_head() == before
    committed = handler.commit()
    index.append(entries=committed, height=3)
    assert index.get(source) is original
    assert index.get(relation) is original_edge
    assert encode_envelope(original_edge.envelope) == original_bytes
    assert original_edge.artifact.created_at == NOW
    assert original_edge.ledger_entry.height == 2
    assert index.relations() == ()
    assert index.relations(include_revoked=True) == (original_edge,)
    assert index.outgoing_relations(source) == index.incoming_relations(target) == ()
    assert len(index.contributions()) == 2
    assert len(index.artifacts()) == 4
    assert len(index.revocations()) == 1
    restored = CometBFTCallbackHandler(validator=validator(), store=store)
    assert restored.committed_head() == handler.committed_head()
    with pytest.raises(ValueError, match="UNAUTHORIZED_REVOCATION"):
        CometBFTCallbackHandler(
            validator=TransactionValidator(expected_chain_id=CHAIN), store=store
        )
    rebuilt = KnowledgeGraphIndex()
    saved = store.load()
    assert saved is not None
    rebuilt.refresh(saved)
    assert rebuilt.contributions() == index.contributions()
    assert rebuilt.relations() == index.relations()
    # Historical snapshot sees the graph before revocation.
    rebuilt.refresh(snapshot)
    assert len(rebuilt.relations()) == 1
    executor = GraphQLQueryExecutor(queries=KnowledgeGraphQueries(index=index))
    response = executor.execute(
        """query($ref: ID!) {
            contributions { title }
            relations { kind }
            history: relations(includeRevoked: true, kind: ABOUT) { artifactRef revoked }
            artifact(ref: $ref) { artifactRef ... on Relation { revoked } }
            revocations(target: $ref) { targetRef reason signerPublicKey height }
        }""",
        variables={"ref": str(relation)},
    )
    assert response.succeeded and response.data is not None
    assert response.data["relations"] == []
    assert response.data["history"] == [{"artifactRef": str(relation), "revoked": True}]
    assert response.data["artifact"] == {
        "artifactRef": str(relation),
        "revoked": True,
    }
    assert response.data["revocations"] == [
        {
            "targetRef": str(relation),
            "reason": "Correct area placement",
            "signerPublicKey": VALIDATOR_KEY.hex(),
            "height": "3",
        }
    ]
    audit = executor.execute(
        "query($ref: ID!) { artifact(ref: $ref) { ... on EdgeRevocation { targetRef reason } } }",
        variables={"ref": str(artifact_ref(tx.envelopes[0]))},
    )
    assert audit.succeeded and audit.data is not None
    assert audit.data["artifact"] == {
        "targetRef": str(relation),
        "reason": "Correct area placement",
    }
    assert cli(("query", "--ledger-path", str(tmp_path / "ledger.sqlite"), "revocations")) == 0
    assert len(json.loads(capsys.readouterr().out)["artifacts"]) == 1
    for extra, count in [((), 0), (("--include-revoked",), 1)]:
        assert (
            cli(("query", "--ledger-path", str(tmp_path / "ledger.sqlite"), "relations", *extra))
            == 0
        )
        assert len(json.loads(capsys.readouterr().out)["artifacts"]) == count


def test_rejected_revocation_aborts_an_entire_replacement_transaction(tmp_path: Path) -> None:
    snapshot, source, target, old = fixture()
    store = SQLiteArtifactLedgerStore(path=tmp_path / "ledger.sqlite")
    store.save(snapshot)
    handler = CometBFTCallbackHandler(validator=validator(), store=store)
    replacement = ContributionRelation(
        kind=RelationKind.CITES, from_contribution=source, to_contribution=target, created_at=NOW
    )
    tx = transaction(replacement, revoke(old))  # creator has no voting power
    before = handler.committed_head()
    result = handler.finalize_block(height=3, transactions=(encode_transaction(tx),))
    assert result.transaction_results[0].code is TransactionCode.UNAUTHORIZED_REVOCATION
    assert result.state_hash == before.state_hash
    assert handler.commit() == ()
    authorized = transaction(replacement, revoke(old), key=VALIDATOR)
    assert (
        handler.finalize_block(height=4, transactions=(encode_transaction(authorized),))
        .transaction_results[0]
        .code
        is TransactionCode.ACCEPTED
    )
    handler.commit()
    saved = store.load()
    assert saved is not None
    index = KnowledgeGraphIndex()
    index.refresh(saved)
    assert tuple(r.artifact for r in index.relations()) == (replacement,)
    assert index.get(old) is not None


def test_revocation_is_permanent_but_a_new_assertion_is_independent(tmp_path: Path) -> None:
    snapshot, source, target, old = fixture()
    store = SQLiteArtifactLedgerStore(path=tmp_path / "ledger.sqlite")
    store.save(snapshot)
    handler = CometBFTCallbackHandler(validator=validator(), store=store)
    withdrawal = transaction(revoke(old), key=VALIDATOR)
    handler.finalize_block(height=3, transactions=(encode_transaction(withdrawal),))
    handler.commit()

    # An author can assert the same relationship again, without restoring the old edge.
    replacement = transaction(
        ContributionRelation(
            kind=RelationKind.ABOUT,
            from_contribution=source,
            to_contribution=target,
            created_at=NOW + timedelta(seconds=1),
        )
    )
    new = artifact_ref(replacement.envelopes[0])
    assert new != old
    assert handler.check_tx(encode_transaction(replacement)).code is TransactionCode.ACCEPTED
    handler.finalize_block(height=4, transactions=(encode_transaction(replacement),))
    handler.commit()
    # Replaying the original edge cannot bring it back.
    assert (
        handler.check_tx(encode_transaction(snapshot.entries[1].transaction)).code
        is TransactionCode.DUPLICATE
    )
    # Another signed withdrawal with a backdated timestamp has the same permanent effect.
    backdated = transaction(
        EdgeRevocation(target=old, reason="Independent audit", created_at=NOW - timedelta(days=1)),
        key=VALIDATOR,
    )
    result = handler.finalize_block(height=5, transactions=(encode_transaction(backdated),))
    assert result.transaction_results[0].code is TransactionCode.ACCEPTED
    handler.commit()
    saved = store.load()
    assert saved is not None and saved.entries[:2] == snapshot.entries
    index = KnowledgeGraphIndex()
    index.refresh(saved)
    assert tuple(r.artifact_ref for r in index.relations()) == (new,)
    assert tuple(r.artifact_ref for r in index.relations(include_revoked=True)) == (old, new)
    assert len(index.revocations(old)) == 2
    assert index.revocations(new) == ()
    assert index.outgoing_relations(source) == index.incoming_relations(target) == index.relations()


def test_snapshot_export_rechecks_authority_from_pinned_genesis(tmp_path: Path) -> None:
    snapshot, _, _, edge = fixture()
    store = SQLiteArtifactLedgerStore(path=tmp_path / "ledger.sqlite")
    store.save(snapshot)
    handler = CometBFTCallbackHandler(validator=validator(), store=store)
    handler.finalize_block(
        height=3, transactions=(encode_transaction(transaction(revoke(edge), key=VALIDATOR)),)
    )
    handler.commit()
    genesis = tmp_path / "genesis.json"
    digest = write_genesis(genesis)
    with pytest.raises(ValueError, match="UNAUTHORIZED_REVOCATION"):
        export_baseline(
            ledger=tmp_path / "ledger.sqlite", output=tmp_path / "without-authority", chain_id=CHAIN
        )
    manifest = export_baseline(
        ledger=tmp_path / "ledger.sqlite",
        output=tmp_path / "baseline",
        chain_id=CHAIN,
        genesis=genesis,
        genesis_sha256=digest,
    )
    assert manifest.genesis_sha256 == digest
    assert manifest.state_hash == handler.committed_head().state_hash.hex()
    assert manifest.payload_counts["edge_revocation"] == 1


def test_genesis_authority_is_hash_pinned_and_chain_bound(tmp_path: Path) -> None:
    path = tmp_path / "genesis.json"
    digest = write_genesis(path)
    assert load_voting_power(chain_id=CHAIN, genesis=path, genesis_sha256=digest) == {
        VALIDATOR_KEY: 1
    }
    assert load_voting_power(chain_id=CHAIN, genesis=None, genesis_sha256=None) == {}
    for chain, genesis, pin in [
        ("wrong", path, digest),
        (CHAIN, path, "0" * 64),
        (CHAIN, None, digest),
        (CHAIN, path, None),
    ]:
        with pytest.raises(ValueError):
            load_voting_power(chain_id=chain, genesis=genesis, genesis_sha256=pin)


@pytest.mark.parametrize(
    "mutation", ["duplicate", "wrong-key-type", "bad-key", "zero", "negative", "bool", "empty"]
)
def test_malformed_electorates_fail_closed(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "genesis.json"
    write_genesis(path)
    data = json.loads(path.read_text())
    validators = data["validators"]
    if mutation == "duplicate":
        validators.append(validators[0])
    elif mutation == "wrong-key-type":
        validators[0]["pub_key"]["type"] = "tendermint/PubKeySecp256k1"
    elif mutation == "bad-key":
        validators[0]["pub_key"]["value"] = "!"
    elif mutation == "empty":
        validators.clear()
    else:
        validators[0]["power"] = {"zero": 0, "negative": -1, "bool": True}[mutation]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_voting_power(
            chain_id=CHAIN, genesis=path, genesis_sha256=sha256(path.read_bytes()).hexdigest()
        )


def test_init_chain_cannot_substitute_a_different_electorate(tmp_path: Path) -> None:
    from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2 as abci
    from discovery_net._cometbft.v0_40.tendermint.crypto.keys_pb2 import PublicKey
    from discovery_net.node.abci import CometBFTABCIAdapter

    handler = CometBFTCallbackHandler(
        validator=validator(), store=SQLiteArtifactLedgerStore(path=tmp_path / "ledger.sqlite")
    )
    adapter = CometBFTABCIAdapter(handler=handler)
    for key, power in [(VALIDATOR_KEY, 2), (AUTHOR_KEY, 1)]:
        with pytest.raises(ValueError, match="pinned genesis"):
            adapter.init_chain(
                abci.RequestInitChain(
                    chain_id=CHAIN,
                    initial_height=1,
                    validators=[abci.ValidatorUpdate(pub_key=PublicKey(ed25519=key), power=power)],
                )
            )
    assert (
        adapter.init_chain(
            abci.RequestInitChain(
                chain_id=CHAIN,
                initial_height=1,
                validators=[
                    abci.ValidatorUpdate(pub_key=PublicKey(ed25519=VALIDATOR_KEY), power=1)
                ],
            )
        ).app_hash
        == LocalArtifactLedger().state_hash()
    )


def test_new_targets_and_relations_to_revocations_are_rejected() -> None:
    snapshot, source, target, edge = fixture()
    ledger = LocalArtifactLedger(entries=snapshot.entries)
    new_edge = ContributionRelation(
        kind=RelationKind.CITES, from_contribution=source, to_contribution=target, created_at=NOW
    )
    new = transaction(new_edge, key=VALIDATOR)
    together = transaction(new_edge, revoke(artifact_ref(new.envelopes[0])), key=VALIDATOR)
    assert (
        validator().validate(encode_transaction(together), ledger).code
        is TransactionCode.MISSING_REFERENCE
    )
    withdrawal = transaction(revoke(edge), key=VALIDATOR)
    ledger, _ = ledger.append_transaction(entry(withdrawal, 3))
    relation = transaction(
        ContributionRelation(
            from_contribution=source,
            to_contribution=artifact_ref(withdrawal.envelopes[0]),
            kind=RelationKind.CITES,
            created_at=NOW,
        )
    )
    assert (
        validator().validate(encode_transaction(relation), ledger).code
        is TransactionCode.MISSING_REFERENCE
    )
