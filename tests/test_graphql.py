from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.entrypoints.graphql import GraphQLQueryExecutor
from discovery_net.indexing import KnowledgeGraphIndex
from discovery_net.knowledge_graph import (
    Artifact,
    ArtifactRef,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.node import ArtifactLedgerEntry, ArtifactLedgerSnapshot
from discovery_net.query import KnowledgeGraphQueries
from discovery_net.wire import artifact_ref, sign_artifact, sign_transaction

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
NOW = datetime(2026, 8, 26, 18, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _GraphFixture:
    graphql: GraphQLQueryExecutor
    references: dict[str, ArtifactRef]


def test_graphql_composes_filtered_search_and_nested_graph_traversal() -> None:
    # One operation finds a problem and follows its areas, proofs, assessments, and replies.
    graph = _graph_fixture()

    result = graph.graphql.execute(
        """
        query Research($title: String!) {
          indexedHeight
          problems: contributions(
            kind: PROBLEM_STATEMENT
            titleContains: $title
          ) {
            artifactRef
            title
            body
            areas: outgoingContributions(
              via: ABOUT
              kind: MATHEMATICAL_AREA
            ) {
              artifactRef
              title
            }
            proofs: incomingContributions(
              via: ABOUT
              kind: PROOF_ATTEMPT
            ) {
              artifactRef
              title
              supportingContributions: incomingContributions(via: SUPPORTS) {
                kind
                title
              }
              contradictingContributions: incomingContributions(via: CONTRADICTS) {
                kind
                title
              }
              replies: incomingContributions(via: REPLIES_TO, kind: DISCUSSION) {
                kind
                title
              }
            }
          }
        }
        """,
        variables={"title": "riemann"},
        operation_name="Research",
    )

    assert result.succeeded
    assert result.errors == ()
    assert result.data == {
        "indexedHeight": "1",
        "problems": [
            {
                "artifactRef": graph.references["problem"],
                "title": "The Riemann Hypothesis",
                "body": "All non-trivial zeros have real part one half.",
                "areas": [
                    {
                        "artifactRef": graph.references["area"],
                        "title": "Number theory",
                    }
                ],
                "proofs": [
                    {
                        "artifactRef": graph.references["proof"],
                        "title": "A spectral proof attempt",
                        "supportingContributions": [
                            {"kind": "DISCUSSION", "title": "Promising reduction"}
                        ],
                        "contradictingContributions": [
                            {"kind": "OBJECTION", "title": "Domain mismatch"}
                        ],
                        "replies": [
                            {"kind": "DISCUSSION", "title": "Could the domain be restricted?"}
                        ],
                    }
                ],
            }
        ],
    }


def test_graphql_exposes_signed_relation_artifacts_and_resolved_endpoints() -> None:
    # Raw relation fields retain attribution and consensus provenance beside node traversal.
    graph = _graph_fixture()

    result = graph.graphql.execute(
        """
        query Relation($ref: ID!) {
          artifact(ref: $ref) {
            __typename
            artifactRef
            chainId
            signerPublicKey
            signature
            height
            transactionIndex
            createdAt
            ... on Relation {
              kind
              fromContributionRef
              toContributionRef
              source { artifactRef title }
              destination { artifactRef title }
            }
          }
        }
        """,
        variables={"ref": graph.references["proof_about_problem"]},
    )

    assert result.succeeded
    assert result.data is not None
    artifact = result.data["artifact"]
    assert isinstance(artifact, dict)
    assert artifact["__typename"] == "Relation"
    assert artifact["artifactRef"] == graph.references["proof_about_problem"]
    assert artifact["chainId"] == CHAIN_ID
    assert artifact["signerPublicKey"] == PRIVATE_KEY.public_key().public_bytes_raw().hex()
    assert len(artifact["signature"]) == 128
    assert artifact["height"] == "1"
    assert artifact["transactionIndex"] == "8"
    assert artifact["createdAt"] == "2026-08-26T18:00:00+00:00"
    assert artifact["kind"] == "ABOUT"
    assert artifact["fromContributionRef"] == graph.references["proof"]
    assert artifact["toContributionRef"] == graph.references["problem"]
    assert artifact["source"] == {
        "artifactRef": graph.references["proof"],
        "title": "A spectral proof attempt",
    }
    assert artifact["destination"] == {
        "artifactRef": graph.references["problem"],
        "title": "The Riemann Hypothesis",
    }


def test_graphql_reports_invalid_references_as_operation_errors() -> None:
    # Invalid graph identifiers remain explicit GraphQL errors rather than ambiguous empty results.
    graph = _graph_fixture()

    result = graph.graphql.execute('{ artifact(ref: "not-a-cid") { artifactRef } }')

    assert not result.succeeded
    assert result.data == {"artifact": None}
    assert result.errors[0]["message"] == "artifact reference must be a valid CID"
    assert result.errors[0]["path"] == ["artifact"]


def _graph_fixture() -> _GraphFixture:
    entries: list[ArtifactLedgerEntry] = []
    references: dict[str, ArtifactRef] = {}

    references["area"] = _append(
        entries,
        Contribution(
            kind=ContributionKind.MATHEMATICAL_AREA,
            title="Number theory",
            body="The study of integers.",
            created_at=NOW,
        ),
    )
    references["problem"] = _append(
        entries,
        Contribution(
            kind=ContributionKind.PROBLEM_STATEMENT,
            title="The Riemann Hypothesis",
            body="All non-trivial zeros have real part one half.",
            created_at=NOW,
        ),
    )
    references["proof"] = _append(
        entries,
        _contribution(ContributionKind.PROOF_ATTEMPT, "A spectral proof attempt"),
    )
    references["support"] = _append(
        entries,
        _contribution(ContributionKind.DISCUSSION, "Promising reduction"),
    )
    references["objection"] = _append(
        entries,
        _contribution(ContributionKind.OBJECTION, "Domain mismatch"),
    )
    references["reply"] = _append(
        entries,
        _contribution(
            ContributionKind.DISCUSSION,
            "Could the domain be restricted?",
        ),
    )
    references["reply_to_proof"] = _append(
        entries,
        _relation(references["reply"], references["proof"], RelationKind.REPLIES_TO),
    )
    references["problem_about_area"] = _append(
        entries,
        _relation(references["problem"], references["area"], RelationKind.ABOUT),
    )
    references["proof_about_problem"] = _append(
        entries,
        _relation(references["proof"], references["problem"], RelationKind.ABOUT),
    )
    references["supports_proof"] = _append(
        entries,
        _relation(references["support"], references["proof"], RelationKind.SUPPORTS),
    )
    references["contradicts_proof"] = _append(
        entries,
        _relation(references["objection"], references["proof"], RelationKind.CONTRADICTS),
    )

    index = KnowledgeGraphIndex()
    index.refresh(ArtifactLedgerSnapshot(height=1, entries=tuple(entries)))
    return _GraphFixture(
        graphql=GraphQLQueryExecutor(queries=KnowledgeGraphQueries(index=index)),
        references=references,
    )


def _append(entries: list[ArtifactLedgerEntry], artifact: Artifact) -> ArtifactRef:
    envelope = sign_artifact(
        chain_id=CHAIN_ID,
        artifact=artifact,
        private_key=PRIVATE_KEY,
    )
    entry = ArtifactLedgerEntry(
        transaction=sign_transaction(envelopes=(envelope,), private_key=PRIVATE_KEY),
        height=1,
        transaction_index=len(entries),
    )
    entries.append(entry)
    return artifact_ref(envelope)


def _contribution(
    kind: ContributionKind,
    title: str,
) -> Contribution:
    return Contribution(
        kind=kind,
        title=title,
        body=f"Body for {title}",
        created_at=NOW,
    )


def _relation(
    source: ArtifactRef,
    destination: ArtifactRef,
    kind: RelationKind,
) -> ContributionRelation:
    return ContributionRelation(
        from_contribution=source,
        to_contribution=destination,
        kind=kind,
        created_at=NOW,
    )
