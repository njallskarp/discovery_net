# Defines the two CometBFT controls governing which peer addresses may coexist.

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class PeerAdmissionPolicy:
    """Configures address routability checks and duplicate-IP admission."""

    address_book_strict: bool = True
    allow_duplicate_ip: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.address_book_strict, bool):
            raise TypeError("address_book_strict must be a boolean")
        if not isinstance(self.allow_duplicate_ip, bool):
            raise TypeError("allow_duplicate_ip must be a boolean")
