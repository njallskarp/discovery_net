# Projects local node and ledger observations into browser-safe snapshots.

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from ipaddress import IPv4Address, ip_address
from threading import RLock
from typing import final

from discovery_net.artifacts import ArtifactRef
from discovery_net.domains.math import Contribution, ContributionRelation
from discovery_net.indexing import IndexedArtifact, KnowledgeGraphIndex
from discovery_net.inspector.models import (
    InspectorContribution,
    InspectorContributionSummary,
    InspectorFeedPage,
    InspectorFeedTransaction,
    InspectorKnowledgeGraph,
    InspectorNode,
    InspectorNodeSnapshot,
    InspectorPeer,
    InspectorRelation,
    InspectorRelationSummary,
    InspectorSnapshot,
    NodeObservation,
)
from discovery_net.inspector.sources import (
    ArtifactLedgerReader,
    ArtifactLedgerUpdate,
    NodeObservationSource,
)

_DEFAULT_FEED_LIMIT = 20
_MAX_FEED_LIMIT = 50


@final
class InspectorService:
    """Builds sanitized read-only views from node and committed ledger state."""

    __slots__ = (
        "_clock",
        "_index",
        "_indexed_chain_id",
        "_indexed_height",
        "_ledger_reader",
        "_lock",
        "_node_source",
        "_redact_peer_ips",
    )

    def __init__(
        self,
        *,
        node_source: NodeObservationSource,
        ledger_reader: ArtifactLedgerReader,
        redact_peer_ips: bool = True,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(redact_peer_ips, bool):
            raise TypeError("redact_peer_ips must be a boolean")
        if not callable(clock):
            raise TypeError("clock must be callable")

        self._node_source = node_source
        self._ledger_reader = ledger_reader
        self._redact_peer_ips = redact_peer_ips
        self._clock = clock
        self._index = KnowledgeGraphIndex()
        self._indexed_height: int | None = None
        self._indexed_chain_id: str | None = None
        self._lock = RLock()

    def snapshot(self) -> InspectorSnapshot:
        """Return the latest internally consistent inspector snapshot."""
        node = self._observe_node()

        with self._lock:
            self._synchronize(node.chain_id)
            observed_at = self._clock()
            return InspectorSnapshot(
                observed_at=observed_at,
                node=_node_view(node, redact_peer_ips=self._redact_peer_ips),
                knowledge_graph=_knowledge_graph_view(self._index),
            )

    def node_snapshot(self) -> InspectorNodeSnapshot:
        """Return current node and peer status without reading the artifact ledger."""
        node = self._observe_node()
        return InspectorNodeSnapshot(
            observed_at=self._clock(),
            node=_node_view(node, redact_peer_ips=self._redact_peer_ips),
        )

    def knowledge_graph(self, *, after_height: int | None = None) -> InspectorKnowledgeGraph:
        """Return full topology or only artifacts committed after a known height."""
        if after_height is not None:
            _require_nonnegative_integer(after_height, "after_height")
        node = self._observe_node()
        with self._lock:
            self._synchronize(node.chain_id)
            if after_height is not None and after_height > self._index.indexed_height:
                raise ValueError("after_height must not exceed the indexed height")
            return _knowledge_graph_view(self._index, after_height=after_height)

    def feed_page(
        self,
        *,
        before: tuple[int, int] | None = None,
        limit: int = _DEFAULT_FEED_LIMIT,
    ) -> InspectorFeedPage:
        """Return one reverse-chronological page of committed transactions."""
        _require_nonnegative_integer(limit, "limit")
        if not 1 <= limit <= _MAX_FEED_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_FEED_LIMIT}")
        if before is not None:
            if not isinstance(before, tuple) or len(before) != 2:
                raise TypeError("before must be a height and transaction-index tuple")
            _require_nonnegative_integer(before[0], "before height")
            _require_nonnegative_integer(before[1], "before transaction index")

        node = self._observe_node()
        with self._lock:
            self._synchronize(node.chain_id)
            return _feed_page(self._index, before=before, limit=limit)

    def contribution(self, artifact_ref: ArtifactRef) -> InspectorContribution | None:
        """Return one full contribution body and provenance by artifact reference."""
        if not isinstance(artifact_ref, str):
            raise TypeError("artifact_ref must be a string")
        node = self._observe_node()
        with self._lock:
            self._synchronize(node.chain_id)
            indexed = self._index.get(artifact_ref)
            if indexed is None or not isinstance(indexed.artifact, Contribution):
                return None
            return _contribution_view(indexed)

    def _observe_node(self) -> NodeObservation:
        node = self._node_source.observe()
        if not isinstance(node, NodeObservation):
            raise TypeError("node source must return a NodeObservation")
        return node

    def _synchronize(self, node_chain_id: str) -> None:
        if self._indexed_chain_id is not None and self._indexed_chain_id != node_chain_id:
            raise ValueError("node chain does not match the indexed artifact ledger")
        update = self._ledger_reader.updates_after(self._index.indexed_height)
        if not isinstance(update, ArtifactLedgerUpdate):
            raise TypeError("ledger reader must return an ArtifactLedgerUpdate")
        self._advance_index(update, node_chain_id)

    def _advance_index(
        self,
        update: ArtifactLedgerUpdate,
        node_chain_id: str,
    ) -> None:
        if self._indexed_chain_id is not None and self._indexed_chain_id != node_chain_id:
            raise ValueError("node chain does not match the indexed artifact ledger")
        if self._indexed_height is not None and update.height < self._indexed_height:
            raise ValueError("artifact ledger moved behind the indexed height")
        if update.height == self._indexed_height and not update.entries:
            return

        ledger_chain_id = _update_chain_id(update)
        if ledger_chain_id is not None and ledger_chain_id != node_chain_id:
            raise ValueError("node chain does not match the artifact ledger")
        if self._indexed_chain_id is not None and ledger_chain_id not in {
            None,
            self._indexed_chain_id,
        }:
            raise ValueError("artifact ledger contains multiple chains")
        self._index.append(entries=update.entries, height=update.height)
        self._indexed_height = update.height
        if ledger_chain_id is not None:
            self._indexed_chain_id = ledger_chain_id


def _update_chain_id(update: ArtifactLedgerUpdate) -> str | None:
    chain_ids = {entry.transaction.chain_id for entry in update.entries}
    if len(chain_ids) > 1:
        raise ValueError("artifact ledger contains multiple chains")
    return next(iter(chain_ids), None)


def _node_view(node: NodeObservation, *, redact_peer_ips: bool) -> InspectorNode:
    return InspectorNode(
        node_id=node.node_id,
        moniker=node.moniker,
        chain_id=node.chain_id,
        version=node.version,
        latest_height=node.latest_height,
        application_height=node.application_height,
        latest_block_time=node.latest_block_time,
        catching_up=node.catching_up,
        validator_power=node.validator_power,
        mempool_transactions=node.mempool_transactions,
        consensus_round=node.consensus_round,
        consensus_step=node.consensus_step,
        peers=tuple(
            InspectorPeer(
                node_id=peer.node_id,
                moniker=peer.moniker,
                observed_address=(
                    _redacted_ip(peer.remote_ip) if redact_peer_ips else peer.remote_ip
                ),
                direction=peer.direction,
                connected_seconds=peer.connected_seconds,
                bytes_sent=peer.bytes_sent,
                bytes_received=peer.bytes_received,
            )
            for peer in node.peers
        ),
    )


def _redacted_ip(value: str) -> str:
    try:
        address = ip_address(value)
    except ValueError:
        return "redacted"
    if isinstance(address, IPv4Address):
        first, second, *_remaining = str(address).split(".")
        return f"{first}.{second}.x.x"
    first, second, *_remaining = address.exploded.split(":")
    return f"{first}:{second}::/32"


def _knowledge_graph_view(
    index: KnowledgeGraphIndex,
    *,
    after_height: int | None = None,
) -> InspectorKnowledgeGraph:
    contributions = index.contributions()
    relations = index.relations()
    if after_height is not None:
        contributions = tuple(
            indexed for indexed in contributions if indexed.ledger_entry.height > after_height
        )
        relations = tuple(
            indexed for indexed in relations if indexed.ledger_entry.height > after_height
        )
    return InspectorKnowledgeGraph(
        indexed_height=index.indexed_height,
        contributions=tuple(_contribution_summary(indexed) for indexed in contributions),
        relations=tuple(_relation_summary(indexed) for indexed in relations),
    )


def _feed_page(
    index: KnowledgeGraphIndex,
    *,
    before: tuple[int, int] | None,
    limit: int,
) -> InspectorFeedPage:
    grouped: dict[tuple[int, int], list[IndexedArtifact]] = {}
    for indexed in index.artifacts():
        key = (
            indexed.ledger_entry.height,
            indexed.ledger_entry.transaction_index,
        )
        grouped.setdefault(key, []).append(indexed)

    positions = sorted(grouped, reverse=True)
    if before is not None:
        positions = [position for position in positions if position < before]
    selected = positions[:limit]
    transactions = tuple(
        _feed_transaction(position, tuple(grouped[position])) for position in selected
    )
    next_before = None
    if len(positions) > limit and selected:
        next_before = f"{selected[-1][0]}:{selected[-1][1]}"
    return InspectorFeedPage(
        indexed_height=index.indexed_height,
        transactions=transactions,
        next_before=next_before,
    )


def _feed_transaction(
    position: tuple[int, int],
    artifacts: tuple[IndexedArtifact, ...],
) -> InspectorFeedTransaction:
    return InspectorFeedTransaction(
        height=position[0],
        transaction_index=position[1],
        contributions=tuple(
            _contribution_view(indexed)
            for indexed in artifacts
            if isinstance(indexed.artifact, Contribution)
        ),
        relations=tuple(
            _relation_view(indexed)
            for indexed in artifacts
            if isinstance(indexed.artifact, ContributionRelation)
        ),
    )


def _contribution_summary(indexed: IndexedArtifact) -> InspectorContributionSummary:
    artifact = indexed.artifact
    if not isinstance(artifact, Contribution):
        raise TypeError("indexed artifact must be a Contribution")
    return InspectorContributionSummary(
        artifact_ref=indexed.artifact_ref,
        kind=artifact.kind,
        title=artifact.title,
        created_at=artifact.created_at,
        height=indexed.ledger_entry.height,
        transaction_index=indexed.ledger_entry.transaction_index,
        artifact_index=indexed.artifact_index,
    )


def _relation_summary(indexed: IndexedArtifact) -> InspectorRelationSummary:
    artifact = indexed.artifact
    if not isinstance(artifact, ContributionRelation):
        raise TypeError("indexed artifact must be a ContributionRelation")
    return InspectorRelationSummary(
        artifact_ref=indexed.artifact_ref,
        kind=artifact.kind,
        from_contribution=artifact.from_contribution,
        to_contribution=artifact.to_contribution,
        created_at=artifact.created_at,
        height=indexed.ledger_entry.height,
        transaction_index=indexed.ledger_entry.transaction_index,
        artifact_index=indexed.artifact_index,
    )


def _contribution_view(indexed: IndexedArtifact) -> InspectorContribution:
    artifact = indexed.artifact
    if not isinstance(artifact, Contribution):
        raise TypeError("indexed artifact must be a Contribution")
    return InspectorContribution(
        artifact_ref=indexed.artifact_ref,
        kind=artifact.kind,
        title=artifact.title,
        body=artifact.body,
        created_at=artifact.created_at,
        signer_public_key=indexed.envelope.signer_public_key.hex(),
        signature=indexed.envelope.signature.hex(),
        height=indexed.ledger_entry.height,
        transaction_index=indexed.ledger_entry.transaction_index,
        artifact_index=indexed.artifact_index,
    )


def _relation_view(indexed: IndexedArtifact) -> InspectorRelation:
    artifact = indexed.artifact
    if not isinstance(artifact, ContributionRelation):
        raise TypeError("indexed artifact must be a ContributionRelation")
    return InspectorRelation(
        artifact_ref=indexed.artifact_ref,
        kind=artifact.kind,
        from_contribution=artifact.from_contribution,
        to_contribution=artifact.to_contribution,
        created_at=artifact.created_at,
        signer_public_key=indexed.envelope.signer_public_key.hex(),
        signature=indexed.envelope.signature.hex(),
        height=indexed.ledger_entry.height,
        transaction_index=indexed.ledger_entry.transaction_index,
        artifact_index=indexed.artifact_index,
    )


def _require_nonnegative_integer(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative")
