# Defines observations and presentation data used by the read-only inspector.

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    field_validator,
)

from discovery_net.knowledge_graph import ContributionKind, RelationKind

type NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
type PositiveInt = Annotated[int, Field(strict=True, gt=0)]


class _InspectorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ConnectionDirection(StrEnum):
    """The side that initiated one observed peer connection."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class PeerObservation(_InspectorModel):
    """Raw metadata observed or reported for one direct CometBFT peer."""

    node_id: StrictStr
    moniker: StrictStr
    remote_ip: StrictStr
    direction: ConnectionDirection
    connected_seconds: NonNegativeInt
    bytes_sent: NonNegativeInt
    bytes_received: NonNegativeInt

    @field_validator("node_id", "moniker", "remote_ip")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("peer text fields must not be blank")
        return value


class NodeObservation(_InspectorModel):
    """The latest local observation of one CometBFT node."""

    node_id: StrictStr
    moniker: StrictStr
    chain_id: StrictStr
    version: StrictStr
    latest_height: NonNegativeInt
    application_height: NonNegativeInt
    latest_block_time: AwareDatetime
    catching_up: StrictBool
    validator_power: NonNegativeInt
    mempool_transactions: NonNegativeInt
    consensus_round: NonNegativeInt
    consensus_step: StrictStr
    peers: tuple[PeerObservation, ...]

    @field_validator("node_id", "moniker", "chain_id", "version", "consensus_step")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("node text fields must not be blank")
        return value


class InspectorPeer(_InspectorModel):
    """Sanitized direct-peer data safe to expose to the browser."""

    node_id: StrictStr
    moniker: StrictStr
    observed_address: StrictStr
    direction: ConnectionDirection
    connected_seconds: NonNegativeInt
    bytes_sent: NonNegativeInt
    bytes_received: NonNegativeInt


class InspectorNode(_InspectorModel):
    """Local node status and its direct peer observations."""

    node_id: StrictStr
    moniker: StrictStr
    chain_id: StrictStr
    version: StrictStr
    latest_height: NonNegativeInt
    application_height: NonNegativeInt
    latest_block_time: AwareDatetime
    catching_up: StrictBool
    validator_power: NonNegativeInt
    mempool_transactions: NonNegativeInt
    consensus_round: NonNegativeInt
    consensus_step: StrictStr
    peers: tuple[InspectorPeer, ...]


class InspectorContribution(_InspectorModel):
    """A committed contribution projected for graph inspection."""

    artifact_ref: StrictStr
    kind: ContributionKind
    title: StrictStr
    body: StrictStr
    created_at: AwareDatetime
    signer_public_key: StrictStr
    signature: StrictStr
    height: PositiveInt
    transaction_index: NonNegativeInt


class InspectorRelation(_InspectorModel):
    """A committed directed relation projected for graph inspection."""

    artifact_ref: StrictStr
    kind: RelationKind
    from_contribution: StrictStr
    to_contribution: StrictStr
    created_at: AwareDatetime
    signer_public_key: StrictStr
    signature: StrictStr
    height: PositiveInt
    transaction_index: NonNegativeInt


class InspectorKnowledgeGraph(_InspectorModel):
    """The locally indexed committed contribution graph."""

    indexed_height: NonNegativeInt
    contributions: tuple[InspectorContribution, ...]
    relations: tuple[InspectorRelation, ...]


class InspectorSnapshot(_InspectorModel):
    """One internally consistent browser view of local node state."""

    observed_at: AwareDatetime
    node: InspectorNode
    knowledge_graph: InspectorKnowledgeGraph

    @field_validator("observed_at")
    @classmethod
    def require_aware_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value
