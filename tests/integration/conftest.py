# Provides shared prerequisites for live CometBFT integration tests.

import os
import shutil
from pathlib import Path

import pytest

_COMETBFT_BINARY_ENV = "DISCOVERY_NET_COMETBFT_BINARY"


@pytest.fixture(scope="session")
def cometbft_binary() -> Path:
    """Return the configured CometBFT executable or skip when none is available."""
    configured = os.environ.get(_COMETBFT_BINARY_ENV)
    if configured is not None:
        binary = Path(configured)
        if not binary.is_file():
            raise AssertionError(f"configured CometBFT binary does not exist: {binary}")
        return binary

    discovered = shutil.which("cometbft")
    if discovered is None:
        pytest.skip(f"CometBFT is not installed and {_COMETBFT_BINARY_ENV} is not configured")
    return Path(discovered)
