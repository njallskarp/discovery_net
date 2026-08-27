# Generates validator identities and provisions them into fresh CometBFT homes.

from __future__ import annotations

from pathlib import Path
from typing import final

from discovery_net.node.runtime._cometbft_config import _CometBFTConfig
from discovery_net.node.runtime._cometbft_home import _CometBFTHome
from discovery_net.node.runtime._cometbft_process import _CometBFTProcess
from discovery_net.node.runtime._validator_identity_files import _VerifiedValidatorIdentity
from discovery_net.node.runtime.genesis import GenesisTrustAnchor, _VerifiedGenesis
from discovery_net.node.runtime.genesis_validator import GenesisValidator
from discovery_net.node.runtime.validator_identity import ValidatorIdentity


@final
class CometBFTValidatorProvisioner:
    """Owns fresh validator identity generation and one-time home provisioning."""

    __slots__ = ("_process",)

    def __init__(self, *, binary: Path = Path("cometbft")) -> None:
        if not isinstance(binary, Path):
            raise TypeError("binary must be a Path")
        self._process = _CometBFTProcess(binary=binary)

    def initialize_home(self, *, home: Path) -> ValidatorIdentity:
        """Atomically create an unstarted home with a new validator identity."""
        if not isinstance(home, Path):
            raise TypeError("home must be a Path")
        if home.exists():
            raise FileExistsError(f"CometBFT home already exists: {home}")
        self._process.require_compatible_command_surface()
        return _CometBFTHome(
            path=home,
            config=_CometBFTConfig(),
            process=self._process,
        ).provision_validator()

    def genesis_validator(
        self,
        identity: ValidatorIdentity,
        *,
        name: str,
        voting_power: int,
    ) -> GenesisValidator:
        """Return the shareable public descriptor of one pristine identity."""
        if not isinstance(identity, ValidatorIdentity):
            raise TypeError("identity must be a ValidatorIdentity")
        return _VerifiedValidatorIdentity.from_identity(identity).genesis_validator(
            name=name,
            voting_power=voting_power,
        )

    def install_genesis(
        self,
        *,
        identity: ValidatorIdentity,
        genesis_path: Path,
        genesis_trust_anchor: GenesisTrustAnchor,
    ) -> None:
        """Bind a pristine validator home to one exact shared network genesis."""
        if not isinstance(identity, ValidatorIdentity):
            raise TypeError("identity must be a ValidatorIdentity")
        if not isinstance(genesis_path, Path):
            raise TypeError("genesis_path must be a Path")
        if not isinstance(genesis_trust_anchor, GenesisTrustAnchor):
            raise TypeError("genesis_trust_anchor must be a GenesisTrustAnchor")

        genesis = _VerifiedGenesis.from_path(
            path=genesis_path,
            trust_anchor=genesis_trust_anchor,
        )
        _CometBFTHome(
            path=identity.directory,
            config=_CometBFTConfig(),
            process=self._process,
        ).install_validator_genesis(
            genesis=genesis,
        )
