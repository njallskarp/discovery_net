"""The domain boundary is usable without mathematical models or new wire types."""

from dataclasses import dataclass
from typing import cast

import pytest

from discovery_net.artifacts import ArtifactRef
from discovery_net.artifacts.encoding import CodecError, canonical_json
from discovery_net.domains.base import ArtifactDomain
from discovery_net.domains.math import (
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.domains.math.codec import MATH_DOMAIN
from discovery_net.knowledge_graph import (
    ArtifactRef as LegacyRef,
)
from discovery_net.knowledge_graph import (
    Contribution as LegacyContribution,
)
from discovery_net.knowledge_graph import (
    ContributionKind as LegacyKind,
)
from discovery_net.knowledge_graph import (
    ContributionRelation as LegacyRelation,
)
from discovery_net.knowledge_graph import (
    RelationKind as LegacyRelationKind,
)
from discovery_net.wire import PayloadType, decode_payload


@dataclass(frozen=True)
class _SecurityFinding:
    component: str


class _SecurityDomain:
    """A deliberately tiny test adapter; it is not registered on the network."""

    def encode(self, artifact: _SecurityFinding) -> tuple[str, bytes]:
        if not artifact.component.strip():
            raise ValueError("component is required")
        return "security.finding", canonical_json({"component": artifact.component})

    def decode(self, payload_type: str, data: bytes) -> _SecurityFinding:
        import json

        value = json.loads(data)
        if payload_type != "security.finding" or not isinstance(value, dict):
            raise ValueError("unsupported security payload")
        if set(value) != {"component"} or not isinstance(value["component"], str):
            raise ValueError("invalid security fields")
        artifact = _SecurityFinding(component=value["component"])
        if self.encode(artifact)[1] != data:
            raise ValueError("noncanonical security payload")
        return artifact

    def is_node(self, artifact: _SecurityFinding) -> bool:
        return True

    def references(self, artifact: _SecurityFinding) -> tuple[ArtifactRef, ...]:
        return ()


def _round_trip[T](domain: ArtifactDomain[T], artifact: T) -> T:
    payload_type, encoded = domain.encode(artifact)
    return domain.decode(payload_type, encoded)


def test_old_import_paths_export_the_same_classes_and_enum_members() -> None:
    assert LegacyRef is ArtifactRef
    assert LegacyContribution is Contribution
    assert LegacyKind is ContributionKind
    assert LegacyRelation is ContributionRelation
    assert LegacyRelationKind is RelationKind
    assert LegacyKind.LEMMA is ContributionKind.LEMMA


def test_second_domain_round_trips_through_the_shared_contract() -> None:
    domain: ArtifactDomain[_SecurityFinding] = _SecurityDomain()
    finding = _SecurityFinding(component="parser")

    assert _round_trip(domain, finding) == finding
    assert domain.is_node(finding)
    assert domain.references(finding) == ()
    with pytest.raises(ValueError, match="component"):
        _round_trip(domain, _SecurityFinding(component=""))


def test_a_domain_adapter_does_not_enable_new_live_payload_types() -> None:
    payload_type, encoded = _SecurityDomain().encode(_SecurityFinding(component="parser"))

    with pytest.raises(CodecError, match="not supported"):
        decode_payload(cast(PayloadType, payload_type), encoded)
    with pytest.raises(CodecError, match="not supported"):
        MATH_DOMAIN.decode(payload_type, encoded)
    with pytest.raises(ValueError):
        PayloadType(payload_type)
