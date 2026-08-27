import pytest

from discovery_net.wire import TRANSACTION_LIMITS, TransactionLimit, TransactionLimitError


def test_protocol_transaction_limits_are_explicit_and_stable() -> None:
    assert TRANSACTION_LIMITS.maximum_encoded_bytes == 4 * 1024 * 1024
    assert TRANSACTION_LIMITS.maximum_artifacts == 256


def test_encoded_size_accepts_the_boundary_and_rejects_one_byte_over() -> None:
    TRANSACTION_LIMITS.require_encoded_size(bytes(TRANSACTION_LIMITS.maximum_encoded_bytes))

    with pytest.raises(TransactionLimitError, match="encoded bytes") as raised:
        TRANSACTION_LIMITS.require_encoded_size(bytes(TRANSACTION_LIMITS.maximum_encoded_bytes + 1))

    assert raised.value.limit is TransactionLimit.ENCODED_BYTES


def test_artifact_count_accepts_the_boundary_and_rejects_one_artifact_over() -> None:
    TRANSACTION_LIMITS.require_artifact_count(TRANSACTION_LIMITS.maximum_artifacts)

    with pytest.raises(TransactionLimitError, match="artifacts") as raised:
        TRANSACTION_LIMITS.require_artifact_count(TRANSACTION_LIMITS.maximum_artifacts + 1)

    assert raised.value.limit is TransactionLimit.ARTIFACT_COUNT
