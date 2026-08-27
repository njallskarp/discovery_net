"""1. Agent creates artifacts
2. ArtifactSubmitter signs an atomic transaction
3. ArtifactSubmitter broadcasts it to local CometBFT
4. CometBFT validates it through CheckTx
5. CometBFT gossips it to peers
6. Validators agree on a block
7. Every CometBFT node calls its local CometBFTCallbackHandler
8. The handler calls local_artifact_ledger.append_transaction(...)
9. CometBFT calls Commit
10. Discovery Net persists the resulting local artifact ledger
11. Local graph indexers process the committed artifacts"""
