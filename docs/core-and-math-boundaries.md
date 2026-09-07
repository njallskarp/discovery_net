# Core and math boundaries

This refactor preserves the existing network format and default graph behavior.
It does not register additional domains with the running network or introduce a
new topology, validator role, or public version selector.

| Package | Responsibility |
|---|---|
| `artifacts` | Shared identifiers, canonical JSON, immutable signed-record index, and domain-independent graph projection |
| `domains.base` | Deterministic payload encoding/decoding, node classification, and node-reference extraction contract |
| `domains.math` | Existing mathematical vocabulary/models, legacy payload validation, and the default math projection |
| `wire` | Existing signed envelope/transaction format; explicitly delegates payload handling to the math domain |
| `node` | Chain, signature, resource, duplicate, and reference checks plus deterministic ledger execution |
| `indexing` / `query` | Compatibility math query interfaces over raw artifacts and the selected graph projection |
| `development` | Read-only verified ledger export for offline experiments |

`discovery_net.knowledge_graph` and its original submodules re-export the same
model, enum, and identifier objects from their new homes. Existing import paths,
enum values, signing bytes, IDs, and raw GraphQL provenance remain supported.
`ArtifactDomain` is a code contract, not a plugin registry: implementing an adapter
does not make its payload type admissible in the live wire protocol.

## Raw artifacts and projected structure

`ArtifactIndex` stores `IndexedEnvelope` records and original ledger provenance.
Its updates return a new index, preserving existing records. `GraphProjection`
interprets each record as a `GraphNode`, a `GraphEdge`, or an omitted artifact.
`ProjectedGraph` builds direction and kind indexes over that selection. Edges to
nodes excluded by the projection do not participate in traversal. Raw lookup still
returns every original record.

`KnowledgeGraphIndex` defaults to `LegacyMathProjection`, retaining current math
query APIs. Its `artifacts()` and `get()` methods are raw-history accessors with
decoded math payloads; `contributions()`, `relations()`, and directed traversals
use the projection. `raw_index` exposes the immutable envelope index directly.
The compatibility layer caches decoded artifacts and retains their object identity
across incremental updates. A failed refresh or append publishes neither a partial
raw index nor a partial projection.

Development code can pass a different fixed projection to `KnowledgeGraphIndex` or
build multiple `ProjectedGraph` instances over a shared `ArtifactIndex`. Projection
policies must be deterministic and fixed for an index's lifetime. Use a rebuild
when changing policy; no public CLI or GraphQL projection switch is added here.
This layer does not authorize new assertions or modify historical records.

## Compatibility evidence

`tests/fixtures/legacy_graph/history.json` contains fixed signed bytes, IDs, block
results, state hashes, and a graph query captured before the refactor. Preserve
that fixture unchanged. Tests cover both replay and incremental projection, plus
third-party assertions, forward references, rejected transactions, and restart.

The second-domain tests demonstrate the contracts without enabling security
payloads on the network. The offline exporter is documented in
[`development/README.md`](../src/discovery_net/development/README.md).
