# Verifies exact genesis identity and the Discovery Net InitChain invariants.

import hashlib
import json
from pathlib import Path

import pytest

from discovery_net.node.runtime import GenesisTrustAnchor
from discovery_net.node.runtime.genesis import _VerifiedGenesis
from tests.runtime_test_support import CHAIN_ID, write_genesis


@pytest.mark.parametrize("initial_height", (None, 0, "0", 1, "1"))
def test_genesis_accepts_forms_with_effective_initial_height_one(
    tmp_path: Path,
    initial_height: int | str | None,
) -> None:
    document: dict[str, object] = {"chain_id": CHAIN_ID}
    if initial_height is not None:
        document["initial_height"] = initial_height
    content = json.dumps(document, separators=(",", ":")).encode()
    path = tmp_path / "genesis.json"
    anchor = write_genesis(path, content)

    verified = _VerifiedGenesis.from_path(path=path, trust_anchor=anchor)

    assert verified.content == content
    assert verified.document.effective_initial_height == 1


@pytest.mark.parametrize("app_state", ({}, []))
def test_genesis_rejects_nonempty_application_state(
    tmp_path: Path,
    app_state: object,
) -> None:
    content = json.dumps({"chain_id": CHAIN_ID, "app_state": app_state}).encode()
    path = tmp_path / "genesis.json"
    anchor = write_genesis(path, content)

    with pytest.raises(ValueError, match="absent or null"):
        _VerifiedGenesis.from_path(path=path, trust_anchor=anchor)


def test_genesis_accepts_null_application_state_as_empty_abci_bytes(tmp_path: Path) -> None:
    content = json.dumps({"chain_id": CHAIN_ID, "app_state": None}).encode()
    path = tmp_path / "genesis.json"
    anchor = write_genesis(path, content)

    verified = _VerifiedGenesis.from_path(path=path, trust_anchor=anchor)

    assert verified.content == content


def test_genesis_rejects_a_wrong_digest_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "genesis.json"
    path.write_bytes(b"not JSON")
    anchor = GenesisTrustAnchor(
        expected_chain_id=CHAIN_ID,
        expected_sha256=hashlib.sha256(b"different bytes").hexdigest(),
    )

    with pytest.raises(ValueError, match="SHA-256"):
        _VerifiedGenesis.from_path(path=path, trust_anchor=anchor)


def test_genesis_rejects_a_chain_id_collision_in_operator_configuration(tmp_path: Path) -> None:
    path = tmp_path / "genesis.json"
    anchor = write_genesis(path)
    wrong_anchor = GenesisTrustAnchor(
        expected_chain_id="another-chain",
        expected_sha256=anchor.expected_sha256.upper(),
    )

    with pytest.raises(ValueError, match="chain ID"):
        _VerifiedGenesis.from_path(path=path, trust_anchor=wrong_anchor)
