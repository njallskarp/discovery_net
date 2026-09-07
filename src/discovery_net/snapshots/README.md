# Verified ledger snapshots

Create a consistent baseline without writing to the source ledger:

```sh
python -m discovery_net.snapshots baseline \
  --ledger /path/to/live/artifact-ledger.sqlite \
  --output /path/to/new/baseline-directory \
  --chain-id discovery-net
```

The output directory must not exist. The tool pins a SQLite read snapshot, copies
it with the backup API (including committed WAL data), checks SQLite integrity,
and replays every copied transaction with the expected chain ID. It creates a
standalone `ledger.sqlite` and publishes `manifest.json` last. Consumers must
require the manifest: an interrupted publication without it is not a baseline.
Failed exports do not overwrite an existing destination or modify the source.

The manifest records the captured height, recomputed application state hash,
transaction/artifact counts, file checksum/size, and capture time. An editable
checkout also records its Git revision and whether source files are dirty;
installed packages without a detectable checkout report these fields as null.
For reproducible experiments, capture from a clean, committed source revision.

Replay checks the internal consistency of the supplied ledger; it does not fetch
or authenticate a consensus block header. The state hash is recomputed from the
copied ledger, not independently attested by validators. An empty ledger contains
no signed chain identity, so its manifest sets `chain_id_verified` to false.

The command runs offline and does not submit artifacts, connect to network
peers, or change node startup behavior. Keep real baselines out of source control.

For a ledger containing revocations, supply `--genesis /path/to/genesis.json` and
`--genesis-sha256 TRUSTED_DIGEST`. Replay derives validator authority from that
hash-verified public genesis and records its digest in the manifest. Without it,
revocations fail authorization and the export is rejected. Retain the matching
public genesis alongside the backup for future verification.
