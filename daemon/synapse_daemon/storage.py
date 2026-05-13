"""SQLite-backed storage layer (Contracts #8, #9, #11).

Owns the connection lifetime, ensures WAL + foreign-keys, applies migrations
on open. The connection is shared across the daemon — SQLite in WAL mode is
fine for our request volume, and the connection itself is created with
``check_same_thread=False`` because FastAPI may dispatch handlers across
threads.

For Milestone B this module's job is:

  • Open ``data/synapse.sqlite``.
  • Run all unapplied migrations.
  • Expose ``conn`` and a ``transaction()`` context manager for callers.

The dedicated CRUD modules (``projects.py``, ``tools.py``, ``audit.py``) layer
on top in later milestones.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .migrations import list_migrations
from .migrations._runner import apply_pending

DEFAULT_DB_FILENAME = "synapse.sqlite"


class Storage:
    """Thin wrapper around a single SQLite connection."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / DEFAULT_DB_FILENAME
        self._conn: sqlite3.Connection | None = None

    # ── lifecycle ────────────────────────────────────────────────────────

    def open(self) -> None:
        if self._conn is not None:
            return
        # ``isolation_level=None`` puts the driver in autocommit mode so we
        # can run BEGIN/COMMIT manually from the migration runner and from
        # ``transaction()`` below.
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        # WAL + sensible synchronous mode — durable enough for a personal
        # daemon, no fsync per write.
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")  # ms

    def close(self) -> None:
        if self._conn is None:
            return
        self._conn.close()
        self._conn = None

    # ── accessors ────────────────────────────────────────────────────────

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Storage.open() must be called first")
        return self._conn

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    # ── transactions ─────────────────────────────────────────────────────

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block in an exclusive transaction.

        Commits on normal exit, rolls back on exception.
        """

        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")

    # ── migrations ───────────────────────────────────────────────────────

    def migrate(self) -> list[int]:
        """Apply every unapplied migration. Returns the numbers applied."""

        return apply_pending(self.conn, list_migrations())

    def applied_migration_numbers(self) -> set[int]:
        cursor = self.conn.execute("SELECT number FROM schema_migrations")
        return {row["number"] for row in cursor.fetchall()}

    def schema_migration(self) -> int:
        """Highest applied migration number, or ``0`` if none yet."""

        try:
            return max(self.applied_migration_numbers(), default=0)
        except sqlite3.OperationalError:
            return 0
