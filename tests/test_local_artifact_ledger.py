from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import Contribution, ContributionKind
from discovery_net.node import AppendOutcome, ArtifactLedgerEntry, LocalArtifactLedger
from discovery_net.wire import SignedEnvelope, artifact_ref, sign_artifact

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
SECOND_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))


def signed_envelope(
    title: str,
    *,
    private_key: Ed25519PrivateKey = PRIVATE_KEY,
) -> SignedEnvelope:
    return sign_artifact(
        chain_id=CHAIN_ID,
        artifact=Contribution(
            kind=ContributionKind.PROBLEM_STATEMENT,
            title=title,
            body=f"Body for {title}",
            created_at=datetime(2026, 8, 24, 12, 30, tzinfo=UTC),
        ),
        private_key=private_key,
    )


def entry(
    title: str,
    *,
    height: int = 1,
    transaction_index: int = 0,
    private_key: Ed25519PrivateKey = PRIVATE_KEY,
) -> ArtifactLedgerEntry:
    return ArtifactLedgerEntry(
        envelope=signed_envelope(title, private_key=private_key),
        height=height,
        transaction_index=transaction_index,
    )


def test_state_hash_has_fixed_vectors_for_ordered_entries() -> None:
    empty = LocalArtifactLedger()
    first, _ = empty.append_artifact(entry("First"))
    second, _ = first.append_artifact(entry("Second", transaction_index=2))

    assert empty.state_hash().hex() == (
        "658209c56cbbf49d7da1e00b6393fe444854670953c5e48cfa791f0fb750cb07"
    )
    assert first.state_hash().hex() == (
        "0c86756587c6d668dfa8547620b488cb98f4a646017a1f1e35678407d8bc39b9"
    )
    assert second.state_hash().hex() == (
        "f2283ca03d032196e7bef10667a5b569fe888f03fb522f131aaf9e8503516492"
    )


def test_append_returns_a_new_ledger_without_changing_the_original() -> None:
    empty = LocalArtifactLedger()
    first_entry = entry("First")

    resulting, outcome = empty.append_artifact(first_entry)

    assert outcome is AppendOutcome.ACCEPTED
    assert empty.entries() == ()
    assert not empty.contains(artifact_ref(first_entry.envelope))
    assert resulting.entries() == (first_entry,)
    assert resulting.contains(artifact_ref(first_entry.envelope))


def test_duplicate_append_returns_the_same_ledger() -> None:
    first_entry = entry("First")
    ledger = LocalArtifactLedger(entries=(first_entry,))
    duplicate = ArtifactLedgerEntry(
        envelope=first_entry.envelope,
        height=2,
        transaction_index=0,
    )

    resulting, outcome = ledger.append_artifact(duplicate)

    assert outcome is AppendOutcome.DUPLICATE
    assert resulting is ledger


@pytest.mark.parametrize(
    ("height", "transaction_index"),
    [(2, 4), (2, 3), (1, 99)],
)
def test_append_rejects_nonincreasing_block_positions(
    height: int,
    transaction_index: int,
) -> None:
    ledger = LocalArtifactLedger(entries=(entry("First", height=2, transaction_index=4),))

    with pytest.raises(ValueError, match="follow the current ledger position"):
        ledger.append_artifact(entry("Second", height=height, transaction_index=transaction_index))


def test_constructor_restores_the_same_ledger_from_ordered_entries() -> None:
    entries = (
        entry("First"),
        entry("Second", transaction_index=2),
        entry("Third", height=3),
    )
    restored = LocalArtifactLedger(entries=entries)
    appended = LocalArtifactLedger()
    for ledger_entry in entries:
        appended, outcome = appended.append_artifact(ledger_entry)
        assert outcome is AppendOutcome.ACCEPTED

    assert restored == appended
    assert restored.entries() == entries
    assert restored.state_hash() == appended.state_hash()


def test_constructor_rejects_duplicate_artifacts() -> None:
    first_entry = entry("First")
    duplicate = ArtifactLedgerEntry(
        envelope=first_entry.envelope,
        height=1,
        transaction_index=1,
    )

    with pytest.raises(ValueError, match="duplicate artifacts"):
        LocalArtifactLedger(entries=(first_entry, duplicate))


def test_constructor_rejects_noncanonical_entry_order() -> None:
    with pytest.raises(ValueError, match="increasing block position order"):
        LocalArtifactLedger(
            entries=(
                entry("Second", height=2),
                entry("First", height=1),
            )
        )


def test_state_hash_commits_to_envelope_and_block_position() -> None:
    state_hashes = {
        LocalArtifactLedger(entries=(entry("First"),)).state_hash(),
        LocalArtifactLedger(entries=(entry("Other"),)).state_hash(),
        LocalArtifactLedger(entries=(entry("First", height=2),)).state_hash(),
        LocalArtifactLedger(entries=(entry("First", transaction_index=1),)).state_hash(),
        LocalArtifactLedger(entries=(entry("First", private_key=SECOND_PRIVATE_KEY),)).state_hash(),
    }

    assert len(state_hashes) == 5


def test_artifact_identity_includes_the_signer() -> None:
    first_entry = entry("First")
    ledger = LocalArtifactLedger(entries=(first_entry,))
    second_signer = entry("First", private_key=SECOND_PRIVATE_KEY)

    assert ledger.contains(artifact_ref(first_entry.envelope))
    assert not ledger.contains(artifact_ref(second_signer.envelope))


@pytest.mark.parametrize(
    ("height", "transaction_index", "message"),
    [
        (0, 0, "height"),
        (-1, 0, "height"),
        (1 << 63, 0, "height"),
        (1, -1, "transaction_index"),
        (1, 1 << 64, "transaction_index"),
    ],
)
def test_entry_rejects_positions_outside_the_canonical_range(
    height: int,
    transaction_index: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ArtifactLedgerEntry(
            envelope=signed_envelope("First"),
            height=height,
            transaction_index=transaction_index,
        )


@pytest.mark.parametrize(
    ("height", "transaction_index"),
    [(True, 0), (1, False), ("1", 0), (1, "0")],
)
def test_entry_requires_integer_positions(
    height: object,
    transaction_index: object,
) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        ArtifactLedgerEntry(
            envelope=signed_envelope("First"),
            height=height,  # type: ignore[arg-type]
            transaction_index=transaction_index,  # type: ignore[arg-type]
        )


def test_ledger_requires_an_ordered_tuple_and_is_immutable() -> None:
    with pytest.raises(TypeError, match="entries must be a tuple"):
        LocalArtifactLedger(entries=[])  # type: ignore[arg-type]

    ledger = LocalArtifactLedger()
    with pytest.raises(FrozenInstanceError):
        ledger._entries = ()  # type: ignore[misc]


def test_entry_and_ledger_reject_values_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="envelope must be a SignedEnvelope"):
        ArtifactLedgerEntry(
            envelope=object(),  # type: ignore[arg-type]
            height=1,
            transaction_index=0,
        )

    with pytest.raises(TypeError, match="entries must contain ArtifactLedgerEntry"):
        LocalArtifactLedger(entries=(object(),))  # type: ignore[arg-type]
