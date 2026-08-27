# Identifies the inseparable private key and signing-state files of one validator.

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorIdentity:
    """References a private validator key and its matching anti-double-sign state."""

    directory: Path

    def __post_init__(self) -> None:
        if not isinstance(self.directory, Path):
            raise TypeError("directory must be a Path")

    @property
    def key_path(self) -> Path:
        """Return the conventional CometBFT private-validator key path."""
        return self.directory / "config" / "priv_validator_key.json"

    @property
    def state_path(self) -> Path:
        """Return the matching CometBFT private-validator state path."""
        return self.directory / "data" / "priv_validator_state.json"
