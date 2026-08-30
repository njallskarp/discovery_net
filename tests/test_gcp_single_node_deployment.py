from __future__ import annotations

import runpy
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest


def _deployment_root() -> Path:
    return Path(__file__).resolve().parents[1] / "deploy" / "gcp" / "single-node"


def _certificate_validator() -> Callable[..., int]:
    namespace = runpy.run_path(
        str(_deployment_root() / "scripts" / "check-inspector-certificate.py")
    )
    return cast(Callable[..., int], namespace["_validate_certificate"])


def _certificate(*, lifetime_seconds: int = 160 * 60 * 60) -> dict[str, object]:
    now = time.time()
    return {
        "issuer": ((("organizationName", "Let's Encrypt"),),),
        "notBefore": time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(now - 60)),
        "notAfter": time.strftime(
            "%b %d %H:%M:%S %Y GMT",
            time.gmtime(now - 60 + lifetime_seconds),
        ),
        "subjectAltName": (("IP Address", "203.0.113.30"),),
    }


def test_ip_certificate_health_accepts_only_short_lived_lets_encrypt_certificates() -> None:
    validate = _certificate_validator()

    remaining = validate(
        _certificate(),
        address="203.0.113.30",
        tls_mode="ip",
        minimum_valid_seconds=86_400,
    )
    assert remaining > 6 * 24 * 60 * 60

    with pytest.raises(ValueError, match="shortlived"):
        validate(
            _certificate(lifetime_seconds=90 * 24 * 60 * 60),
            address="203.0.113.30",
            tls_mode="ip",
            minimum_valid_seconds=86_400,
        )

    wrong_issuer = _certificate()
    wrong_issuer["issuer"] = ((("organizationName", "Example CA"),),)
    with pytest.raises(ValueError, match="issuer"):
        validate(
            wrong_issuer,
            address="203.0.113.30",
            tls_mode="ip",
            minimum_valid_seconds=86_400,
        )


def test_terraform_contract_defaults_to_ip_https_without_exposing_internal_ports() -> None:
    deployment = _deployment_root()
    main = (deployment / "terraform" / "main.tf").read_text()
    variables = (deployment / "terraform" / "variables.tf").read_text()
    outputs = (deployment / "terraform" / "outputs.tf").read_text()

    assert 'variable "enable_inspector"' in variables
    assert "default     = true" in variables
    assert 'variable "inspector_hostname"' in variables
    assert 'ports    = ["80", "443"]' in main
    assert "count = var.enable_inspector ? 1 : 0" in main
    assert 'ports    = ["26656"]' in main
    assert "source_ranges = sort(tolist(var.trusted_p2p_cidrs))" in main
    assert "26657" not in main
    assert "26658" not in main
    assert "8765" not in main
    assert 'output "inspector_url"' in outputs
    assert '"https://${local.inspector_address}/"' in outputs
