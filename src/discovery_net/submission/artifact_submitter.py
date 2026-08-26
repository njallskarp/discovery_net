# Signs and submits artifacts through a local CometBFT node.

from hashlib import sha256
from typing import final

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import Artifact
from discovery_net.submission._cometbft_rpc_client import _CometBFTRPCClient
from discovery_net.submission.submission_error import SubmissionError
from discovery_net.submission.submission_receipt import SubmissionReceipt
from discovery_net.wire import artifact_ref, encode_envelope, sign_artifact


@final
class ArtifactSubmitter:
    """Signs artifacts and asks a local CometBFT node to broadcast them."""

    __slots__ = ("_private_key", "_rpc_client")

    def __init__(
        self,
        *,
        private_key: Ed25519PrivateKey,
        cometbft_rpc_url: str,
    ) -> None:
        if not isinstance(private_key, Ed25519PrivateKey):
            raise TypeError("private_key must be an Ed25519PrivateKey")

        self._private_key = private_key
        self._rpc_client = _CometBFTRPCClient(url=cometbft_rpc_url)

    def submit(self, artifact: Artifact) -> SubmissionReceipt:
        """Return whether CometBFT accepted a signed artifact for peer broadcast."""
        envelope = sign_artifact(
            chain_id=self._rpc_client.fetch_chain_id(),
            artifact=artifact,
            private_key=self._private_key,
        )
        transaction = encode_envelope(envelope)
        response = self._rpc_client.broadcast_transaction(transaction)
        expected_hash = sha256(transaction).hexdigest().upper()
        if response.transaction_hash != expected_hash:
            raise SubmissionError("CometBFT returned a hash for a different transaction")
        return SubmissionReceipt(
            artifact_ref=artifact_ref(envelope),
            accepted=response.check_tx_code == 0,
        )
