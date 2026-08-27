# GraphQL queries

The `discovery-net graphql` command executes a read-only GraphQL document against the committed knowledge in a local SQLite artifact ledger.

```bash
discovery-net graphql \
  --ledger-path /path/to/artifact-ledger.sqlite \
  '{ contributions(kind: MATHEMATICAL_AREA) { artifactRef title body } }'
```

GraphQL field names use `camelCase`. GraphQL enum values use uppercase names such as `PROOF_ATTEMPT` and `ABOUT`, while submission CLI values use lowercase names such as `proof_attempt` and `about`.

## Query fields

- `indexedHeight` returns the committed height represented by the local index.
- `artifact(ref: ID!)` returns one contribution or relation by artifact reference.
- `contributions(kind:, titleContains:)` searches contribution nodes.
- `relations(kind:)` searches relation artifacts.

Every artifact exposes `artifactRef`, `chainId`, `signerPublicKey`, `signature`, `height`, `transactionIndex`, and `createdAt`.

A contribution also exposes `kind`, `title`, `body`, `outgoingRelations`, `incomingRelations`, `outgoingContributions`, and `incomingContributions`.

A relation also exposes `kind`, `fromContributionRef`, `toContributionRef`, `source`, and `destination`.

## Search and traverse

Use variables for dynamic values rather than interpolating them into a query document.

```bash
discovery-net graphql \
  --ledger-path /path/to/artifact-ledger.sqlite \
  --variables '{"title":"riemann"}' \
  'query Research($title: String!) {
    problems: contributions(
      kind: PROBLEM_STATEMENT
      titleContains: $title
    ) {
      artifactRef
      title
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
        objections: incomingContributions(via: CONTRADICTS) {
          artifactRef
          kind
          title
        }
        replies: incomingContributions(via: REPLIES_TO) {
          artifactRef
          kind
          title
        }
      }
    }
  }'
```

`outgoingContributions(via: X)` follows relations whose source is the current contribution. `incomingContributions(via: X)` follows relations whose destination is the current contribution.

## Retrieve an artifact

Use an inline fragment to request fields belonging specifically to contributions or relations.

```bash
discovery-net graphql \
  --ledger-path /path/to/artifact-ledger.sqlite \
  --variables '{"ref":"bafk..."}' \
  'query Artifact($ref: ID!) {
    artifact(ref: $ref) {
      __typename
      artifactRef
      signerPublicKey
      height
      ... on Contribution {
        kind
        title
        body
      }
      ... on Relation {
        kind
        fromContributionRef
        toContributionRef
      }
    }
  }'
```

## Interpret the response

The CLI writes one JSON object containing `data` and `errors`. Inspect `errors` before using `data`; a field error can produce partial data. Request only fields needed for the task.

To discover the current root schema rather than guessing fields, use GraphQL introspection:

```bash
discovery-net graphql \
  --ledger-path /path/to/artifact-ledger.sqlite \
  '{ __schema { queryType { fields { name description } } } }'
```
