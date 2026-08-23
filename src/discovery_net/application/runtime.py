"""Injectable runtime dependencies used by application workflows."""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from discovery_net.domain import Contribution


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdentifierGenerator(Protocol):
    def new_id(self, namespace: str) -> str: ...


class CandidateSelector(Protocol):
    def choose(self, candidates: Sequence[Contribution]) -> Contribution: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class UuidIdentifierGenerator:
    def new_id(self, namespace: str) -> str:
        return f"{namespace}_{uuid4()}"


class RandomCandidateSelector:
    """Select review work without exposing queue position to the requester."""

    def choose(self, candidates: Sequence[Contribution]) -> Contribution:
        if not candidates:
            raise ValueError("candidates must not be empty")
        return secrets.choice(candidates)
