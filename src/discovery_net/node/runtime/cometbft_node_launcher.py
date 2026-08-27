# Orchestrates trusted preparation and startup of one local CometBFT process.

from pathlib import Path
from typing import NoReturn, final

from discovery_net.node.runtime._cometbft_config import _CometBFTConfig
from discovery_net.node.runtime._cometbft_home import _CometBFTHome
from discovery_net.node.runtime._cometbft_process import _CometBFTProcess
from discovery_net.node.runtime.genesis import _VerifiedGenesis
from discovery_net.node.runtime.node_launch_settings import NodeLaunchSettings


@final
class CometBFTNodeLauncher:
    """Starts CometBFT without provisioning validator identity or membership."""

    __slots__ = ("_binary",)

    def __init__(self, *, binary: Path = Path("cometbft")) -> None:
        if not isinstance(binary, Path):
            raise TypeError("binary must be a Path")
        self._binary = binary

    def start(self, settings: NodeLaunchSettings) -> NoReturn:
        """Verify, prepare, and replace this process with CometBFT."""
        if not isinstance(settings, NodeLaunchSettings):
            raise TypeError("settings must be NodeLaunchSettings")

        genesis = _VerifiedGenesis.from_path(
            path=settings.genesis_path,
            trust_anchor=settings.genesis_trust_anchor,
        )
        process = _CometBFTProcess(binary=self._binary)
        process.require_compatible_command_surface()
        _CometBFTHome(
            path=settings.home,
            config=_CometBFTConfig(),
            process=process,
        ).prepare(genesis=genesis, settings=settings)
        process.exec(
            home=settings.home,
            genesis_sha256=settings.genesis_trust_anchor.expected_sha256,
        )
