from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import Contribution, ContributionKind
from discovery_net.node import AppendOutcome, ArtifactLedgerEntry, LocalArtifactLedger
from discovery_net.wire import SignedTransaction, artifact_ref, sign_artifact, sign_transaction

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
SECOND_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))


def signed_transaction(
    title: str,
    *,
    private_key: Ed25519PrivateKey = PRIVATE_KEY,
) -> SignedTransaction:
    return sign_transaction(
        envelopes=(
            sign_artifact(
                chain_id=CHAIN_ID,
                artifact=Contribution(
                    kind=ContributionKind.PROBLEM_STATEMENT,
                    title=title,
                    body=f"Body for {title}",
                    created_at=datetime(2026, 8, 24, 12, 30, tzinfo=UTC),
                ),
                private_key=private_key,
            ),
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
        transaction=signed_transaction(title, private_key=private_key),
        height=height,
        transaction_index=transaction_index,
    )


def test_state_hash_has_fixed_vectors_for_ordered_entries() -> None:
    empty = LocalArtifactLedger()
    first, _ = empty.append_transaction(entry("First"))
    second, _ = first.append_transaction(entry("Second", transaction_index=2))

    assert empty.state_hash().hex() == (
        "658209c56cbbf49d7da1e00b6393fe444854670953c5e48cfa791f0fb750cb07"
    )
    assert first.state_hash().hex() == (
        "7a9035c712ac6ab9a2358f57580569804b1341794797663a71a897d7c94daff7"
    )
    assert second.state_hash().hex() == (
        "cce7ef2f4b326a344633923526ebc1f965414c215119eb5e1094245a77ab26a8"
    )


def test_append_returns_a_new_ledger_without_changing_the_original() -> None:
    empty = LocalArtifactLedger()
    first_entry = entry("First")

    resulting, outcome = empty.append_transaction(first_entry)

    assert outcome is AppendOutcome.ACCEPTED
    assert empty.entries() == ()
    first_ref = artifact_ref(first_entry.transaction.envelopes[0])
    assert not empty.contains(first_ref)
    assert resulting.entries() == (first_entry,)
    assert resulting.contains(first_ref)
    assert resulting.envelope_by_ref(first_ref) == first_entry.transaction.envelopes[0]


def test_one_ledger_entry_atomically_records_every_transaction_artifact() -> None:
    first_envelope = signed_transaction("First").envelopes[0]
    second_envelope = signed_transaction("Second").envelopes[0]
    transaction = sign_transaction(
        envelopes=(first_envelope, second_envelope),
        private_key=PRIVATE_KEY,
    )
    entry = ArtifactLedgerEntry(transaction=transaction, height=1, transaction_index=0)

    resulting, outcome = LocalArtifactLedger().append_transaction(entry)

    assert outcome is AppendOutcome.ACCEPTED
    assert resulting.entries() == (entry,)
    assert resulting.envelope_by_ref(artifact_ref(first_envelope)) == first_envelope
    assert resulting.envelope_by_ref(artifact_ref(second_envelope)) == second_envelope


def test_duplicate_append_returns_the_same_ledger() -> None:
    first_entry = entry("First")
    ledger = LocalArtifactLedger(entries=(first_entry,))
    duplicate = ArtifactLedgerEntry(
        transaction=first_entry.transaction,
        height=2,
        transaction_index=0,
    )

    resulting, outcome = ledger.append_transaction(duplicate)

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
        ledger.append_transaction(
            entry("Second", height=height, transaction_index=transaction_index)
        )


def test_constructor_restores_the_same_ledger_from_ordered_entries() -> None:
    entries = (
        entry("First"),
        entry("Second", transaction_index=2),
        entry("Third", height=3),
    )
    restored = LocalArtifactLedger(entries=entries)
    appended = LocalArtifactLedger()
    for ledger_entry in entries:
        appended, outcome = appended.append_transaction(ledger_entry)
        assert outcome is AppendOutcome.ACCEPTED

    assert restored == appended
    assert restored.entries() == entries
    assert restored.state_hash() == appended.state_hash()


def test_constructor_rejects_duplicate_artifacts() -> None:
    first_entry = entry("First")
    duplicate = ArtifactLedgerEntry(
        transaction=first_entry.transaction,
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

    assert ledger.contains(artifact_ref(first_entry.transaction.envelopes[0]))
    assert not ledger.contains(artifact_ref(second_signer.transaction.envelopes[0]))


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
            transaction=signed_transaction("First"),
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
            transaction=signed_transaction("First"),
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
    with pytest.raises(TypeError, match="transaction must be a SignedTransaction"):
        ArtifactLedgerEntry(
            transaction=object(),  # type: ignore[arg-type]
            height=1,
            transaction_index=0,
        )

    with pytest.raises(TypeError, match="entries must contain ArtifactLedgerEntry"):
        LocalArtifactLedger(entries=(object(),))  # type: ignore[arg-type]
