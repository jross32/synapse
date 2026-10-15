"""Bounded per-client throttling for public authentication routes.

This intentionally never logs request bodies, passwords, session tokens or OAuth
codes. For multi-replica hosting, replace the in-memory buckets with Redis.
"""
from __future__ import annotations

import threading
import time
from collections import deque


class AuthRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], deque[float]] = {}

    def allow(self, ip: str, endpoint: str, *, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        key = (ip[:128], endpoint[:128])
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] < now - window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            # Bound idle key memory for public exposure.
            if len(self._buckets) > 20000:
                for stale in list(self._buckets)[:2000]:
                    if not self._buckets[stale] or self._buckets[stale][-1] < now - 3600:
                        self._buckets.pop(stale, None)
            return True
