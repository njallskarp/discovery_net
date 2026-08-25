ArtifactSubmitter
    accepts Artifact
    signs and encodes it
    calls _CometBFTRPCClient
    returns SubmissionReceipt

_CometBFTRPCClient
    sends transaction bytes to local CometBFT
    returns _BroadcastResponse
