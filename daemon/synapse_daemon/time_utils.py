"""Timestamp helpers (Contract #24).

Storage layer rule: every timestamp the daemon creates is timezone-aware UTC.
Transport layer: ISO 8601 strings on the wire.
Render layer: UI converts to local via the shared ``formatLocal`` helper in
``renderer/lib/format-time.ts``. Components MUST NOT call ``toLocaleString()``
directly — the helper is the single conversion point.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""

    return datetime.now(timezone.utc)


def to_iso(value: datetime) -> str:
    """Format a datetime as ISO 8601 UTC, accepting both naive and aware inputs.

    Naive datetimes are assumed to be UTC (we never produce naive datetimes
    inside the daemon, but third-party libraries sometimes do).
    """

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def from_iso(text: str) -> datetime:
    """Parse an ISO 8601 string into a timezone-aware UTC ``datetime``.

    Accepts inputs with ``Z`` suffix (which ``fromisoformat`` rejected before
    Python 3.11). Always returns UTC.
    """

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
