"""Contract #28 — snapshot / restore."""

from __future__ import annotations

import pytest

from synapse_daemon.snapshot import (
    SNAPSHOT_FORMAT_VERSION,
    RestoreReport,
    SnapshotPayload,
    assert_compatible,
)


def _payload(schema_migration: int = 2, format_version: int = SNAPSHOT_FORMAT_VERSION) -> SnapshotPayload:
    return SnapshotPayload(
        format_version=format_version,
        schema_migration=schema_migration,
        projects=[{"id": "wbscrper", "name": "Web Scraper"}],
    )


def test_snapshot_records_version_and_format() -> None:
    p = _payload()
    assert p.format_version == SNAPSHOT_FORMAT_VERSION
    assert p.synapse_version
    assert p.exported_at is not None
    assert p.secret_keys == []


def test_restore_report_defaults_to_zero() -> None:
    r = RestoreReport()
    assert r.projects_created == 0
    assert r.warnings == []


def test_compatible_same_version() -> None:
    p = _payload(schema_migration=2)
    warnings = assert_compatible(p, current_schema=2)
    assert warnings == []


def test_compatible_older_schema_warns() -> None:
    p = _payload(schema_migration=1)
    warnings = assert_compatible(p, current_schema=2)
    assert len(warnings) == 1
    assert "older schema" in warnings[0]


def test_incompatible_newer_schema_raises() -> None:
    p = _payload(schema_migration=5)
    with pytest.raises(ValueError) as exc:
        assert_compatible(p, current_schema=2)
    assert "Upgrade the daemon" in str(exc.value)


def test_incompatible_format_version_raises() -> None:
    p = _payload(format_version=999)
    with pytest.raises(ValueError):
        assert_compatible(p, current_schema=2)
