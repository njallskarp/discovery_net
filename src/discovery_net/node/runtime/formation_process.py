# Exposes explicit commands for forming a genesis validator network.

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_public_key
from pydantic import BaseModel, ConfigDict, ValidationError

from discovery_net.node.runtime.cometbft_genesis_writer import CometBFTGenesisWriter
from discovery_net.node.runtime.cometbft_validator_provisioner import (
    CometBFTValidatorProvisioner,
)
from discovery_net.node.runtime.genesis import GenesisTrustAnchor
from discovery_net.node.runtime.genesis_validator import GenesisValidator
from discovery_net.node.runtime.validator_identity import ValidatorIdentity
from discovery_net.node.validator_governance import ValidatorGovernanceConfig


class _HomeOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    home: str


class _ValidatorOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    address: str
    descriptor: str


class _GenesisOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    chain_id: str
    genesis: str
    genesis_sha256: str


class _InstalledGenesisOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    genesis_sha256: str
    home: str


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one explicit network-formation operation and return its exit code."""
    parsed = _argument_parser().parse_args(arguments)
    if parsed.command == "initialize-validator":
        _initialize_validator(parsed)
        return 0
    if parsed.command == "export-validator":
        _export_validator(parsed)
        return 0
    if parsed.command == "create-genesis":
        _create_genesis(parsed)
        return 0
    if parsed.command == "install-genesis":
        _install_genesis(parsed)
        return 0
    raise AssertionError("unknown network-formation command")


def _initialize_validator(arguments: argparse.Namespace) -> None:
    identity = CometBFTValidatorProvisioner(binary=arguments.cometbft_binary).initialize_home(
        home=arguments.home
    )
    _emit(_HomeOutput(home=str(identity.directory)))


def _export_validator(arguments: argparse.Namespace) -> None:
    validator = CometBFTValidatorProvisioner().genesis_validator(
        ValidatorIdentity(directory=arguments.home),
        name=arguments.name,
        voting_power=arguments.voting_power,
    )
    _write_new_public_file(
        arguments.output,
        (validator.model_dump_json(indent=2) + "\n").encode(),
    )
    _emit(
        _ValidatorOutput(
            address=validator.address,
            descriptor=str(arguments.output),
        )
    )


def _create_genesis(arguments: argparse.Namespace) -> None:
    validators = tuple(_read_validator(path) for path in arguments.validators)
    validator_governance = _validator_governance(arguments, validators)
    trust_anchor = CometBFTGenesisWriter(binary=arguments.cometbft_binary).write(
        path=arguments.output,
        chain_id=arguments.chain_id,
        genesis_time=arguments.genesis_time,
        validators=validators,
        validator_governance=validator_governance,
    )
    _emit(
        _GenesisOutput(
            chain_id=trust_anchor.expected_chain_id,
            genesis=str(arguments.output),
            genesis_sha256=trust_anchor.expected_sha256,
        )
    )


def _install_genesis(arguments: argparse.Namespace) -> None:
    trust_anchor = GenesisTrustAnchor(
        expected_chain_id=arguments.chain_id,
        expected_sha256=arguments.genesis_sha256,
    )
    CometBFTValidatorProvisioner().install_genesis(
        identity=ValidatorIdentity(directory=arguments.home),
        genesis_path=arguments.genesis,
        genesis_trust_anchor=trust_anchor,
    )
    _emit(
        _InstalledGenesisOutput(
            genesis_sha256=trust_anchor.expected_sha256,
            home=str(arguments.home),
        )
    )


def _read_validator(path: Path) -> GenesisValidator:
    try:
        return GenesisValidator.model_validate_json(path.read_bytes())
    except OSError as error:
        raise ValueError(f"validator descriptor could not be read: {path}") from error
    except ValidationError as error:
        raise ValueError(f"validator descriptor is invalid: {path}") from error


def _validator_governance(
    arguments: argparse.Namespace,
    validators: tuple[GenesisValidator, ...],
) -> ValidatorGovernanceConfig | None:
    member_paths: list[Path] | None = arguments.governance_members
    threshold: int | None = arguments.governance_threshold
    if member_paths is None:
        if threshold is not None:
            raise ValueError("--governance-threshold requires --governance-member")
        return None
    if threshold is None:
        raise ValueError("--governance-threshold is required with --governance-member")
    member_public_keys = tuple(sorted(_read_ed25519_public_key(path) for path in member_paths))
    return ValidatorGovernanceConfig(
        member_public_keys=member_public_keys,
        approval_threshold=threshold,
        validator_power=validators[0].voting_power,
    )


def _read_ed25519_public_key(path: Path) -> bytes:
    try:
        public_key = load_pem_public_key(path.read_bytes())
    except (OSError, ValueError) as error:
        raise ValueError(f"governance public key could not be read: {path}") from error
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError(f"governance public key must be Ed25519: {path}")
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _write_new_public_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary_path.chmod(0o644)
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            raise FileExistsError(f"validator descriptor already exists: {path}") from None
        _sync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _emit(value: BaseModel) -> None:
    sys.stdout.write(f"{value.model_dump_json()}\n")


def _datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an ISO-8601 datetime") from error


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="discovery-network",
        description="Form a Discovery Net validator network from independent identities.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser(
        "initialize-validator",
        help="create one unstarted validator home",
    )
    initialize.add_argument("--home", required=True, type=Path)
    initialize.add_argument("--cometbft-binary", default=Path("cometbft"), type=Path)

    export = commands.add_parser(
        "export-validator",
        help="write the public genesis descriptor for one validator home",
    )
    export.add_argument("--home", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--name", required=True)
    export.add_argument("--voting-power", default=10, type=int)

    create = commands.add_parser(
        "create-genesis",
        help="form one shared genesis from public validator descriptors",
    )
    create.add_argument("--output", required=True, type=Path)
    create.add_argument("--chain-id", required=True)
    create.add_argument("--genesis-time", required=True, type=_datetime)
    create.add_argument("--validator", dest="validators", action="append", required=True, type=Path)
    create.add_argument(
        "--governance-member",
        dest="governance_members",
        action="append",
        type=Path,
        help="PEM Ed25519 public key authorized to approve validator membership",
    )
    create.add_argument(
        "--governance-threshold",
        type=int,
        help="number of distinct governance-member approvals required",
    )
    create.add_argument("--cometbft-binary", default=Path("cometbft"), type=Path)

    install = commands.add_parser(
        "install-genesis",
        help="bind one unstarted validator home to the exact shared genesis",
    )
    install.add_argument("--home", required=True, type=Path)
    install.add_argument("--genesis", required=True, type=Path)
    install.add_argument("--chain-id", required=True)
    install.add_argument("--genesis-sha256", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
