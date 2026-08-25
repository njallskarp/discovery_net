"""1. Agent creates contribution
2. Client signs it
3. Client broadcasts it to local CometBFT
4. CometBFT validates it through CheckTx
5. CometBFT gossips it to peers
6. Validators agree on a block
7. Every CometBFT node calls its local Discovery Net app
8. The app calls local_artifact_ledger.append_artifact(...)
9. CometBFT calls Commit
10. Discovery Net persists the resulting local artifact ledger
11. Local graph indexers process the committed artifact"""
