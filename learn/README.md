# learn/

Onboarding material for people building or operating `discovery_net`.

## Contents

- **[`learn_discovery_net.htm`](learn_discovery_net.htm)** — a single, dependency-free HTML
  page that teaches the whole system: the contribution/relation domain model, the signed wire
  format (envelopes, transactions, artifact refs), the ABCI application and its CometBFT
  consensus loop, the hash-chained artifact ledger, the end-to-end write lifecycle, the read
  model (index / queries / GraphQL / Inspector), how to run a local network, the Docker
  topology, deployment options, a clickable codebase map, and a glossary. Open it in any
  browser.

## On the root `README.md`

The root [`README.md`](../README.md) is an accurate, copy-pasteable runbook for the workflow it
claims to cover — starting a one-validator network and joining an existing one. It does **not**
mention several things you will still need:

| Not in the root README | Where it is |
| --- | --- |
| `localnet/localnet.sh` (wraps the whole manual flow: `bootstrap`, `join`, `status`, …) | header comment in the script |
| submitting / querying knowledge (`discovery-net submit \| query \| graphql`) | `.agents/skills/discovery-net/` |
| the read-only browser Inspector (`discovery-inspector`) | `src/discovery_net/inspector/` |
| local dev setup (`pip install -e '.[dev]'`, `ruff`/`mypy`/`pytest`) | `.github/workflows/ci.yml`, `pyproject.toml` |
| production cloud deployment | `deploy/gcp/single-node/README.md` |

`learn_discovery_net.htm` covers all of the above.
