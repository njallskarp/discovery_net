# Historical graph compatibility fixture

`history.json` was captured once against unmodified application source at commit
`652f4de5900c19b75af00e0f356a056299797ece`. It is synthetic public test data, not an
export of the running research network. It contains no production keys or identities.

This fixture is a historical contract for the domain/topology refactor. Tests read
the recorded signed bytes, expected CIDs, result codes, state hashes, and query
response directly. They do not regenerate signatures or expected values using the
implementation being tested. Do not refresh these values when changing the codec,
models, validator, store, or index; retain a compatible decoding path instead.

## Contents

- Five consecutive blocks, including an empty fourth block.
- Eight accepted transactions containing twelve distinct artifacts from two signers.
- Mathematics and Combinatorics, with a `subarea_of` assertion placed before its
  source node in the same atomic transaction (an allowed forward reference).
- A problem, proof attempt, counting lemma, and objection with organizational,
  dependency, and contradiction assertions.
- A dependency asserted by a signer who authored neither endpoint, preserving the
  current distinction between authorship and third-party assertions.
- A redundant third-party problem-to-root-area link, which future canonical topology
  selection may omit while raw history remains unchanged.
- A missing endpoint, a duplicate, a bad outer signature, a wrong-chain transaction,
  noncanonical JSON with a trailing newline, and an attempted relation-to-relation
  endpoint. Their numeric result codes and resulting transaction-position gaps are
  pinned. Rejected transactions have no committed artifact references in the manifest.
- One GraphQL query spanning area parents, problem placement, proof dependencies,
  objections, and relation signer/block provenance, with the exact baseline response.

## Capture context

The synthetic signing seeds were the 32-byte sequences `0..31` and `32..63`. These
are deliberately public test keys and must never be used by a live node. Artifact
timestamps were fixed at `2026-09-07T12:00:00Z`; the chain ID is
`discovery-net-legacy-fixture`. Transactions were signed using the baseline wire
implementation, executed through `CometBFTCallbackHandler` with a temporary SQLite
store, and queried through `GraphQLQueryExecutor`. Each expected transaction result
code was specified before execution and checked while capturing the fixture.

The tests execute the frozen history into fresh temporary databases, check every
block result and hash, reopen/replay every possible committed prefix, and verify
both rebuilt and incrementally maintained graph projections. The original research
database is never opened by these tests.

Run with `python -m pytest tests/test_graph_compatibility_contract.py` from the repository
root in an environment with the project's development dependencies installed.
