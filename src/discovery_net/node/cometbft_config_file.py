# Applies Discovery Net's local networking policy to a generated CometBFT config.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import final

from discovery_net.node.cometbft_p2p_config import CometBFTP2PConfig

_P2P_SECTION = "[p2p]"


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class CometBFTConfigFile:
    """Updates the P2P settings that CometBFT does not expose as start flags."""

    path: Path

    def apply_p2p_policy(self, config: CometBFTP2PConfig) -> None:
        """Persist strict-address and duplicate-IP policy without changing other settings."""
        replacements = {
            "addr_book_strict": _toml_boolean(config.addr_book_strict),
            "allow_duplicate_ip": _toml_boolean(config.allow_duplicate_ip),
        }
        remaining = set(replacements)
        in_p2p_section = False
        rendered: list[str] = []

        for line in self.path.read_text().splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                in_p2p_section = stripped == _P2P_SECTION
            key = stripped.partition("=")[0].strip()
            if in_p2p_section and key in remaining:
                newline = "\n" if line.endswith("\n") else ""
                rendered.append(f"{key} = {replacements[key]}{newline}")
                remaining.remove(key)
                continue
            rendered.append(line)

        if remaining:
            missing = ", ".join(sorted(remaining))
            raise ValueError(f"CometBFT P2P config is missing required fields: {missing}")

        temporary_path = self.path.with_suffix(".toml.pending")
        temporary_path.write_text("".join(rendered))
        temporary_path.replace(self.path)


def _toml_boolean(value: bool) -> str:
    return str(value).lower()
