"""Migration runner (Contract #9).

Applies pending migration files in numeric order. Each migration is wrapped in
a manual ``BEGIN/COMMIT`` so partial application is impossible — either every
statement in the file plus the bookkeeping row land together, or none do.

This module deliberately avoids ``executescript()`` because it auto-commits any
pending transaction, defeating the atomicity guarantee we need for
non-idempotent statements like ``ALTER TABLE ... ADD COLUMN`` (which is what
migration ``002`` uses).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from importlib import resources

from . import Migration

# ``_LINE_COMMENT`` strips ``-- ...`` from the end of every line. We don't
# attempt to handle SQL string literals containing ``;`` — none of our
# migrations contain those, and adding one without thinking about this is a
# review-time concern.
_LINE_COMMENT = re.compile(r"--.*$", re.MULTILINE)


def _split_statements(sql: str) -> list[str]:
    """Crude SQL splitter that keeps statements atomic.

    Strips line comments, splits on ``;``, drops empties.
    """

    cleaned = _LINE_COMMENT.sub("", sql)
    parts = [chunk.strip() for chunk in cleaned.split(";")]
    return [p for p in parts if p]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_table_exists(conn: sqlite3.Connection) -> bool:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    )
    return cursor.fetchone() is not None


def _applied_numbers(conn: sqlite3.Connection) -> set[int]:
    cursor = conn.execute("SELECT number FROM schema_migrations")
    return {row[0] for row in cursor.fetchall()}


def apply_pending(conn: sqlite3.Connection, migrations: list[Migration]) -> list[int]:
    """Apply migrations whose number isn't yet in ``schema_migrations``.

    Returns the list of migration numbers actually applied. Idempotent on
    re-run. Caller is responsible for opening the connection in autocommit
    mode so explicit ``BEGIN`` / ``COMMIT`` here work as expected.
    """

    applied: set[int] = _applied_numbers(conn) if _record_table_exists(conn) else set()
    newly_applied: list[int] = []

    pkg = resources.files("synapse_daemon.migrations")
    for migration in migrations:
        if migration.number in applied:
            continue

        sql = pkg.joinpath(migration.filename).read_text(encoding="utf-8")
        statements = _split_statements(sql)

        # A migration that rebuilds a table with child FKs (the SQLite "12-step" ALTER) must run
        # with foreign_keys OFF, or the ``DROP TABLE parent`` fires ``ON DELETE CASCADE`` on children
        # and silently destroys their rows. ``PRAGMA foreign_keys`` is a no-op inside a transaction,
        # so we toggle it in autocommit around BEGIN/COMMIT and validate integrity with
        # ``foreign_key_check`` before committing. Opt-in via a marker (detected on the raw text,
        # since ``_split_statements`` strips comments) so normal migrations keep full FK enforcement.
        fk_off = "runner:foreign_keys=off" in sql

        if fk_off:
            conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in statements:
                conn.execute(stmt)
            if fk_off:
                violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise sqlite3.IntegrityError(
                        f"migration {migration.number} left foreign-key violations: {violations!r}"
                    )
            conn.execute(
                "INSERT INTO schema_migrations (number, slug, applied_at) VALUES (?, ?, ?)",
                (migration.number, migration.slug, _utc_now_iso()),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            if fk_off:
                conn.execute("PRAGMA foreign_keys = ON")

        newly_applied.append(migration.number)

    return newly_applied
