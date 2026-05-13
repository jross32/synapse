"""Contract #24 — timestamps UTC in DB, local in UI."""

from __future__ import annotations

from datetime import datetime, timezone

from synapse_daemon.time_utils import from_iso, to_iso, utc_now


def test_utc_now_returns_aware_utc() -> None:
    n = utc_now()
    assert n.tzinfo is not None
    assert n.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_to_iso_naive_treated_as_utc() -> None:
    naive = datetime(2026, 5, 13, 14, 22, 5)
    out = to_iso(naive)
    assert out.endswith("+00:00")


def test_to_iso_aware_normalised_to_utc() -> None:
    from datetime import timedelta

    aware_plus2 = datetime(2026, 5, 13, 16, 22, 5, tzinfo=timezone(timedelta(hours=2)))
    out = to_iso(aware_plus2)
    assert out.startswith("2026-05-13T14:22:05")
    assert out.endswith("+00:00")


def test_from_iso_accepts_z_suffix() -> None:
    parsed = from_iso("2026-05-13T14:22:05Z")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
    assert parsed.year == 2026 and parsed.hour == 14


def test_from_iso_roundtrip() -> None:
    n = utc_now()
    assert from_iso(to_iso(n)) == n
