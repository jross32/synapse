"""Fail-closed coordination of concurrent AI coding workers.

Workers declare relative file/directory scopes before editing. Overlapping scopes
cannot be leased concurrently. A token fences stale workers after expiry/release.
This complements Git worktrees: isolation prevents accidental shared writes,
while scope leases prevent competing implementations and integration conflicts.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath


class ScopeConflict(RuntimeError):
    pass


def normalize_scope(scope: str) -> str:
    if not isinstance(scope, str) or not scope or "\\" in scope:
        raise ValueError("scope must be a nonempty POSIX-relative path")
    parts = scope.split("/")
    if any(part in ("", ".", "..") for part in parts) or scope.startswith("/"):
        raise ValueError("scope cannot escape or ambiguously address the repository")
    if ":" in scope or any(ord(c) < 32 for c in scope):
        raise ValueError("invalid scope")
    return str(PurePosixPath(scope))


def overlaps(a: str, b: str) -> bool:
    return a == "*" or b == "*" or a == b or a.startswith(b + "/") or b.startswith(a + "/")


@dataclass(frozen=True)
class ScopeLease:
    token: str
    worker_id: str
    scopes: tuple[str, ...]
    expires_at: float


class WorkerScopeCoordinator:
    """In-process primitive; production multi-daemon use needs a durable shared store."""

    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._leases: dict[str, ScopeLease] = {}

    def acquire(self, worker_id: str, scopes: list[str], ttl: float = 300) -> ScopeLease:
        if not worker_id or not worker_id.strip() or not scopes or ttl <= 0:
            raise ValueError("worker, scopes and positive ttl required")
        normalized = tuple(sorted(set(normalize_scope(s) for s in scopes)))
        with self._lock:
            now = self._clock()
            self._prune(now)
            for lease in self._leases.values():
                if any(overlaps(a, b) for a in normalized for b in lease.scopes):
                    raise ScopeConflict(f"scope already leased by worker {lease.worker_id}")
            lease = ScopeLease(uuid.uuid4().hex, worker_id, normalized, now + ttl)
            self._leases[lease.token] = lease
            return lease

    def renew(self, token: str, ttl: float = 300) -> ScopeLease:
        if ttl <= 0:
            raise ValueError("positive ttl required")
        with self._lock:
            now = self._clock()
            self._prune(now)
            lease = self._leases.get(token)
            if lease is None:
                raise ScopeConflict("lease expired or released")
            updated = ScopeLease(token, lease.worker_id, lease.scopes, now + ttl)
            self._leases[token] = updated
            return updated

    def release(self, token: str) -> bool:
        with self._lock:
            return self._leases.pop(token, None) is not None

    def assert_owner(self, token: str, worker_id: str, scope: str) -> None:
        normalized = normalize_scope(scope)
        with self._lock:
            self._prune(self._clock())
            lease = self._leases.get(token)
            if lease is None or lease.worker_id != worker_id or not any(
                normalized == s or normalized.startswith(s + "/") for s in lease.scopes
            ):
                raise ScopeConflict("worker lacks active scope lease")

    def _prune(self, now: float) -> None:
        for token, lease in tuple(self._leases.items()):
            if lease.expires_at <= now:
                del self._leases[token]
