"""Shared canonical encoding primitives, independent of any research domain."""

import json


class CodecError(ValueError):
    """Raised when application bytes do not follow the canonical wire format."""


def canonical_json(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise CodecError("value cannot be represented as canonical JSON") from error
    return encoded.encode("utf-8")
