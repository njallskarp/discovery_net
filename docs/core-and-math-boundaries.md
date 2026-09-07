# Core and math boundaries

This refactor preserves the existing network format and default graph behavior.
It does not register additional domains with the running network or introduce a
new topology, validator role, or public version selector.

| Package | Responsibility |
|---|---|
| `artifacts` | Shared identifiers, canonical JSON, immutable signed-record index, and domain-independent graph projection |
| `domains.base` | Deterministic payload encoding/decoding, node classification, and node-reference extraction contract |
| `domains.math` | Existing mathematical vocabulary/models, payload validation, and the default math projection |
| `wire` | Existing signed envelope/transaction format; explicitly delegates payload handling to the math domain |
| `node` | Chain, signature, resource, duplicate, and reference checks plus deterministic ledger execution |
| `indexing` / `query` | Compatibility math query interfaces over raw artifacts and the selected graph projection |
| `snapshots` | Read-only verified ledger export for offline experiments |

`discovery_net.knowledge_graph` and its original submodules re-export the same
model, enum, and identifier objects from their new homes. Existing import paths,
enum values, signing bytes, IDs, and raw GraphQL provenance remain supported.
`ArtifactDomain` is a code contract, not a plugin registry: implementing an adapter
does not make its payload type admissible in the live wire protocol.

## What moved, what changed, and what is new

| Symbols | Classification and source |
|---|---|
| `Contribution`, `ContributionRelation`, `Artifact` | Moved from `knowledge_graph.models` to [`domains.math.models`](../src/discovery_net/domains/math/models.py); same fields and validation |
| `ContributionKind`, `RelationKind` | Moved from `knowledge_graph.enums` to [`domains.math.enums`](../src/discovery_net/domains/math/enums.py), including all twelve kinds from PR #58 |
| `ArtifactRef` | Moved from `knowledge_graph.identifiers` to `artifacts.identifiers` |
| CID parsing, `CodecError`, canonical JSON | Moved from `wire.codec` to `artifacts.identifiers` / `artifacts.encoding` |
| Payload schemas and codec helpers | Extracted from `wire.codec` to `domains.math.codec`; the signed wire layer delegates to them |
| `ArtifactDomain`, `MathDomain` | New contract and adapter; the adapter uses extracted codecs and node/reference rules formerly in `node.transaction_validator` |
| `IndexedEnvelope`, `ArtifactIndex` | Refactored provenance, raw lookup, and append checks from `IndexedArtifact` / `KnowledgeGraphIndex` in `indexing.knowledge_graph_index` |
| `GraphNode`, `GraphEdge`, `GraphProjection` | New domain-independent selection contracts |
| `ProjectedGraph` | Refactored adjacency/kind indexing from `_GraphState`, `_build_state`, `_append_state`, and `_connect` in `indexing.knowledge_graph_index`, with new selection semantics |
| `MathProjection` | Extracted contribution/relation classification from that index into its permanent math policy |
| `KnowledgeGraphIndex`, `IndexedArtifact` | Refactored in place; retain public query and decoded-record APIs while delegating raw storage and traversal |
| `BaselineManifest`, snapshot exporter | New offline backup, verification, and manifest tooling in `snapshots` |

There is one implementation of the math models and codecs. `knowledge_graph`
imports are intentional public aliases, not copied classes or temporary versions.
The new components above are permanent boundaries, so none has a V2 suffix.
Future temporary replacements must identify their original class/module and carry
a removal TODO under the [integration and release rules](domain-topology-pr-plan.md).

## Raw artifacts and projected structure

`ArtifactIndex` stores `IndexedEnvelope` records and original ledger provenance.
Its updates return a new index, preserving existing records. `GraphProjection`
interprets each record as a `GraphNode`, a `GraphEdge`, or an omitted artifact.
`ProjectedGraph` builds direction and kind indexes over that selection. Edges to
nodes excluded by the projection do not participate in traversal. Raw lookup still
returns every original record.

`KnowledgeGraphIndex` defaults to `MathProjection`, retaining current math
query APIs. Its `artifacts()` and `get()` methods are raw-history accessors with
decoded math payloads; `contributions()`, `relations()`, and directed traversals
use the projection. `raw_index` exposes the immutable envelope index directly.
The compatibility layer caches decoded artifacts and retains their object identity
across incremental updates. A failed refresh or append publishes neither a partial
raw index nor a partial projection.

Callers can pass a different fixed projection to `KnowledgeGraphIndex` or
build multiple `ProjectedGraph` instances over a shared `ArtifactIndex`. Projection
policies must be deterministic and fixed for an index's lifetime. Use a rebuild
when changing policy; no public CLI or GraphQL projection switch is added here.
This layer does not authorize new assertions or modify historical records.

## Compatibility evidence

`tests/fixtures/graph_compatibility/history.json` contains fixed signed bytes, IDs, block
results, state hashes, and a graph query captured before the refactor. Preserve
that fixture unchanged. Tests cover both replay and incremental projection, plus
third-party assertions, forward references, rejected transactions, and restart.

The second-domain tests demonstrate the contracts without enabling security
payloads on the network. The offline exporter is documented in
[`snapshots/README.md`](../src/discovery_net/snapshots/README.md).
