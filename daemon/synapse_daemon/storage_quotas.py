"""Pure quota policy calculations for safe storage reservations.

No network or destructive filesystem operations.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Quota:
    limit_bytes: int
    used_bytes: int
    reserved_bytes: int = 0

    def __post_init__(self):
        if min(self.limit_bytes, self.used_bytes, self.reserved_bytes) < 0:
            raise ValueError("Quota values must be nonnegative")

    @property
    def available_bytes(self) -> int:
        return max(0, self.limit_bytes - self.used_bytes - self.reserved_bytes)

    def can_reserve(self, amount_bytes: int) -> bool:
        if amount_bytes < 0:
            raise ValueError("Reservation cannot be negative")
        return amount_bytes <= self.available_bytes

    def summary(self) -> dict:
        return {
            "limit_bytes": self.limit_bytes,
            "used_bytes": self.used_bytes,
            "reserved_bytes": self.reserved_bytes,
            "available_bytes": self.available_bytes,
            "over_quota": self.used_bytes + self.reserved_bytes > self.limit_bytes,
        }


def enforce_all(amount_bytes: int, *quotas: Quota) -> None:
    """Require all project/user/provider budgets to allow the same reservation."""
    if amount_bytes < 0:
        raise ValueError("Reservation cannot be negative")
    if not quotas:
        raise ValueError("At least one quota is required")
    for quota in quotas:
        if not quota.can_reserve(amount_bytes):
            raise OverflowError("Storage quota exceeded")
