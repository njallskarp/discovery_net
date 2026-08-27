# Verifies narrow and atomic updates to CometBFT's generated P2P configuration.

from pathlib import Path

import pytest

from discovery_net.node import CometBFTConfigFile, CometBFTP2PConfig


def test_p2p_policy_changes_only_the_security_settings(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'moniker = "alice"\n'
        "[p2p]\n"
        'laddr = "tcp://0.0.0.0:26656"\n'
        "addr_book_strict = true\n"
        "allow_duplicate_ip = false\n"
        "[mempool]\n"
        "recheck = true\n"
    )

    CometBFTConfigFile(path=path).apply_p2p_policy(
        CometBFTP2PConfig(
            external_address="127.0.0.1:26656",
            persistent_peers="",
            peer_exchange=True,
            addr_book_strict=False,
            allow_duplicate_ip=True,
        )
    )

    assert path.read_text() == (
        'moniker = "alice"\n'
        "[p2p]\n"
        'laddr = "tcp://0.0.0.0:26656"\n'
        "addr_book_strict = false\n"
        "allow_duplicate_ip = true\n"
        "[mempool]\n"
        "recheck = true\n"
    )


def test_missing_required_p2p_setting_leaves_config_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = "[p2p]\naddr_book_strict = true\n"
    path.write_text(original)

    with pytest.raises(ValueError, match="allow_duplicate_ip"):
        CometBFTConfigFile(path=path).apply_p2p_policy(
            CometBFTP2PConfig(
                external_address="127.0.0.1:26656",
                persistent_peers="",
                peer_exchange=True,
                addr_book_strict=False,
                allow_duplicate_ip=True,
            )
        )

    assert path.read_text() == original
