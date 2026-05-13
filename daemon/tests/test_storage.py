"""Contracts #8, #9 — SQLite storage layer + migration runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_daemon.storage import Storage


def _open(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "data")
    s.open()
    return s


def test_open_creates_db_file(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        assert s.db_path.exists()
        assert s.db_path.name == "synapse.sqlite"
    finally:
        s.close()


def test_wal_mode_set(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        cursor = s.conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0].lower()
        assert mode == "wal"
    finally:
        s.close()


def test_foreign_keys_enabled(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        cursor = s.conn.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1
    finally:
        s.close()


def test_migrate_applies_all_pending(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        applied = s.migrate()
        assert 1 in applied
        assert 2 in applied
        # Tables from 001 + 002 must exist.
        cursor = s.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        for required in (
            "schema_migrations",
            "audit_log",
            "projects",
            "tools",
            "managed_processes",
            "confirm_preferences",
            "settings",
            "project_dependencies",
            "search_index",
            "notification_preferences",
            "project_secrets",
        ):
            assert required in tables, f"Missing table: {required}"
    finally:
        s.close()


def test_migrate_idempotent_on_second_run(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        first = s.migrate()
        second = s.migrate()
        assert len(first) >= 2
        assert second == []  # nothing left to apply
        assert s.applied_migration_numbers() == {1, 2}
    finally:
        s.close()


def test_schema_migration_reports_highest_number(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        assert s.schema_migration() == 0  # no migrations yet
        s.migrate()
        assert s.schema_migration() == 2
    finally:
        s.close()


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        s.migrate()
        with s.transaction() as conn:
            conn.execute(
                "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                ("test", '"hello"', "2026-05-13T00:00:00+00:00"),
            )
        cursor = s.conn.execute("SELECT value_json FROM settings WHERE key='test'")
        assert cursor.fetchone()[0] == '"hello"'
    finally:
        s.close()


def test_transaction_rolls_back_on_exception(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        s.migrate()
        with pytest.raises(RuntimeError):
            with s.transaction() as conn:
                conn.execute(
                    "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                    ("rollback_me", '"x"', "2026-05-13T00:00:00+00:00"),
                )
                raise RuntimeError("force rollback")
        cursor = s.conn.execute("SELECT COUNT(*) FROM settings WHERE key='rollback_me'")
        assert cursor.fetchone()[0] == 0
    finally:
        s.close()


def test_conn_raises_before_open(tmp_path: Path) -> None:
    s = Storage(tmp_path / "data")
    with pytest.raises(RuntimeError):
        _ = s.conn


def test_close_is_idempotent(tmp_path: Path) -> None:
    s = _open(tmp_path)
    s.close()
    s.close()  # must not raise
