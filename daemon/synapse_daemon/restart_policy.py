"""Restart policy per project (Contract #18).

Daemon's process manager consults this on every child exit. Default ``never``
— autonomous restarts are opt-in and bounded.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RestartMode = Literal["never", "on-failure", "always"]


class RestartPolicy(BaseModel):
    """Declarative restart policy."""

    mode: RestartMode = "never"
    max_retries: int = Field(default=3, ge=0, le=100)
    initial_backoff_seconds: int = Field(default=2, ge=1, le=300)
    max_backoff_seconds: int = Field(default=60, ge=1, le=3600)


def should_restart(policy: RestartPolicy, exit_code: int, attempts_so_far: int) -> bool:
    """Return True if the process manager should attempt another restart."""

    if attempts_so_far >= policy.max_retries:
        return False
    if policy.mode == "never":
        return False
    if policy.mode == "always":
        return True
    # on-failure
    return exit_code != 0


def next_backoff_seconds(policy: RestartPolicy, attempts_so_far: int) -> int:
    """Compute the next exponential-backoff delay, capped at ``max_backoff_seconds``.

    Attempt 1 → initial_backoff; attempt 2 → ×2; attempt 3 → ×4; etc.
    """

    if attempts_so_far <= 0:
        return policy.initial_backoff_seconds
    delay = policy.initial_backoff_seconds * (2 ** (attempts_so_far - 1))
    return min(delay, policy.max_backoff_seconds)
