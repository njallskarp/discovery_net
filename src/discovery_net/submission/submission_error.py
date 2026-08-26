# Defines failures at the artifact-submission boundary.


class SubmissionError(RuntimeError):
    """Raised when a local CometBFT node cannot provide a valid broadcast response."""
