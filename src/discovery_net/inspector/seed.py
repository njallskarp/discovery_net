# Provides deterministic node and ledger sources for the inspector demo.

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, final

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.inspector.models import (
    ConnectionDirection,
    NodeObservation,
    PeerObservation,
)
from discovery_net.inspector.service import InspectorService
from discovery_net.inspector.sources import ArtifactLedgerUpdate
from discovery_net.knowledge_graph import (
    ArtifactRef,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.node import ArtifactLedgerEntry, ArtifactLedgerSnapshot
from discovery_net.wire import artifact_ref, sign_artifact, sign_transaction

_CHAIN_ID: Final = "discovery-net-demo"
_BASE_TIME: Final = datetime(2026, 8, 26, 18, tzinfo=UTC)
_SIGNERS: Final = tuple(
    Ed25519PrivateKey.from_private_bytes(bytes(range(offset, offset + 32))) for offset in range(3)
)


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class SeedNodeObservationSource:
    """Returns one deterministic local-node observation for the demo."""

    observation: NodeObservation

    def observe(self) -> NodeObservation:
        """Return the seeded local-node observation."""
        return self.observation


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class SeedArtifactLedgerReader:
    """Returns deterministic committed ledger updates for the demo."""

    snapshot: ArtifactLedgerSnapshot

    def updates_after(self, height: int) -> ArtifactLedgerUpdate:
        """Return seeded entries committed after the supplied height."""
        return ArtifactLedgerUpdate(
            height=self.snapshot.height,
            entries=tuple(entry for entry in self.snapshot.entries if entry.height > height),
        )


def seeded_inspector_service() -> InspectorService:
    """Build an inspector service backed entirely by deterministic seed data."""
    snapshot = seed_ledger_snapshot()
    return InspectorService(
        node_source=SeedNodeObservationSource(observation=_seed_node(snapshot.height)),
        ledger_reader=SeedArtifactLedgerReader(snapshot=snapshot),
    )


def seed_ledger_snapshot() -> ArtifactLedgerSnapshot:
    """Create a small valid mathematical graph from signed network transactions."""
    entries: list[ArtifactLedgerEntry] = []

    number_theory, number_theory_ref = _entry(
        _contribution(
            ContributionKind.MATHEMATICAL_AREA,
            "Number theory",
            "The study of integers, primes, and arithmetic structure.",
            minute=0,
        ),
        signer=_SIGNERS[0],
        height=1,
    )
    entries.append(number_theory)

    analytic_number_theory, analytic_number_theory_ref = _entry(
        _contribution(
            ContributionKind.MATHEMATICAL_AREA,
            "Analytic number theory",
            "Analytic methods applied to questions about integers and primes.",
            minute=1,
        ),
        signer=_SIGNERS[1],
        height=2,
        outgoing=((RelationKind.SUBAREA_OF, number_theory_ref),),
    )
    entries.append(analytic_number_theory)

    problem, problem_ref = _entry(
        _contribution(
            ContributionKind.PROBLEM_STATEMENT,
            "Riemann hypothesis",
            "Every nontrivial zero of the zeta function has real part one half.",
            minute=2,
        ),
        signer=_SIGNERS[0],
        height=3,
        outgoing=((RelationKind.ABOUT, analytic_number_theory_ref),),
    )
    entries.append(problem)

    lemma, lemma_ref = _entry(
        _contribution(
            ContributionKind.LEMMA,
            "Smoothed zero-density estimate",
            "A candidate uniform estimate after applying a compact smoothing kernel.",
            minute=3,
        ),
        signer=_SIGNERS[2],
        height=4,
        outgoing=((RelationKind.ABOUT, problem_ref),),
    )
    entries.append(lemma)

    proof, proof_ref = _entry(
        _contribution(
            ContributionKind.PROOF_ATTEMPT,
            "Trace-formula reduction",
            "Reduce the zero-location claim to positivity of a spectral trace term.",
            minute=4,
        ),
        signer=_SIGNERS[1],
        height=5,
        outgoing=(
            (RelationKind.ABOUT, problem_ref),
            (RelationKind.DEPENDS_ON, lemma_ref),
        ),
    )
    entries.append(proof)

    objection, objection_ref = _entry(
        _contribution(
            ContributionKind.OBJECTION,
            "Uncontrolled boundary term",
            "The proposed trace reduction does not yet bound one boundary contribution.",
            minute=5,
        ),
        signer=_SIGNERS[0],
        height=6,
        outgoing=((RelationKind.CONTRADICTS, proof_ref),),
    )
    entries.append(objection)

    review, review_ref = _entry(
        _contribution(
            ContributionKind.REVIEW,
            "Boundary-term review",
            "The objection is reproducible under the stated normalization.",
            minute=6,
        ),
        signer=_SIGNERS[2],
        height=7,
        outgoing=((RelationKind.SUPPORTS, objection_ref),),
    )
    entries.append(review)

    discussion, _discussion_ref = _entry(
        _contribution(
            ContributionKind.DISCUSSION,
            "Can additional smoothing remove it?",
            "Investigate whether a second smoothing step controls the remaining term.",
            minute=7,
        ),
        signer=_SIGNERS[1],
        height=8,
        outgoing=((RelationKind.REPLIES_TO, review_ref),),
    )
    entries.append(discussion)

    return ArtifactLedgerSnapshot(height=8, entries=tuple(entries))


def _contribution(
    kind: ContributionKind,
    title: str,
    body: str,
    *,
    minute: int,
) -> Contribution:
    return Contribution(
        kind=kind,
        title=title,
        body=body,
        created_at=_BASE_TIME + timedelta(minutes=minute),
    )


def _entry(
    contribution: Contribution,
    *,
    signer: Ed25519PrivateKey,
    height: int,
    outgoing: tuple[tuple[RelationKind, ArtifactRef], ...] = (),
) -> tuple[ArtifactLedgerEntry, ArtifactRef]:
    contribution_envelope = sign_artifact(
        chain_id=_CHAIN_ID,
        artifact=contribution,
        private_key=signer,
    )
    contribution_ref = artifact_ref(contribution_envelope)
    relation_envelopes = tuple(
        sign_artifact(
            chain_id=_CHAIN_ID,
            artifact=ContributionRelation(
                from_contribution=contribution_ref,
                to_contribution=target,
                kind=kind,
                created_at=contribution.created_at,
            ),
            private_key=signer,
        )
        for kind, target in outgoing
    )
    return (
        ArtifactLedgerEntry(
            transaction=sign_transaction(
                envelopes=(contribution_envelope, *relation_envelopes),
                private_key=signer,
            ),
            height=height,
            transaction_index=0,
        ),
        contribution_ref,
    )


def _seed_node(height: int) -> NodeObservation:
    peers = (
        _peer("1" * 40, "helix", "10.42.0.12", ConnectionDirection.OUTBOUND, 4872),
        _peer("2" * 40, "theorem", "10.42.0.18", ConnectionDirection.INBOUND, 3217),
        _peer("3" * 40, "algebra", "192.0.2.24", ConnectionDirection.OUTBOUND, 1904),
        _peer("4" * 40, "proof-lab", "2001:db8:42::7", ConnectionDirection.INBOUND, 733),
    )
    return NodeObservation(
        node_id="a" * 40,
        moniker="local-observer",
        chain_id=_CHAIN_ID,
        version="0.40.0",
        latest_height=height,
        application_height=height,
        latest_block_time=_BASE_TIME + timedelta(minutes=8),
        catching_up=False,
        validator_power=10,
        mempool_transactions=2,
        consensus_round=0,
        consensus_step="commit",
        peers=peers,
    )


def _peer(
    node_id: str,
    moniker: str,
    remote_ip: str,
    direction: ConnectionDirection,
    connected_seconds: int,
) -> PeerObservation:
    return PeerObservation(
        node_id=node_id,
        moniker=moniker,
        remote_ip=remote_ip,
        direction=direction,
        connected_seconds=connected_seconds,
        bytes_sent=connected_seconds * 173,
        bytes_received=connected_seconds * 211,
    )
