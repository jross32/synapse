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
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

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
        # Guards `transaction()` below. One sqlite3.Connection is shared across the whole
        # daemon - the class docstring says so - but nothing serialized access to it. A
        # background task (the health-probe heartbeat) held a transaction open across a
        # network await, and a concurrent HTTP request's own `transaction()` collided with
        # it: `sqlite3.OperationalError: cannot start a transaction within a transaction`.
        #
        # Re-entrant calls on the same thread are supported for legitimate synchronous
        # composition and use SQLite SAVEPOINTs below, preserving nested rollback semantics.
        # This is a safety net, not permission to hold a transaction across external awaits:
        # async routes are regression-tested to release the DB lock before awaited PTY/process
        # work. Other OS threads remain serialized by the RLock.
        self._transaction_lock = threading.RLock()
        self._transaction_state = threading.local()

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

        Commits on normal exit, rolls back on exception. Re-entrant calls on
        the same thread use SQLite savepoints; calls from other threads remain
        serialized around the shared connection.
        """

        conn = self.conn
        self._transaction_lock.acquire()
        depth = getattr(self._transaction_state, "depth", 0)
        savepoint = f"synapse_nested_tx_{depth}"
        nested = depth > 0 or conn.in_transaction
        self._transaction_state.depth = depth + 1
        try:
            if nested:
                conn.execute(f"SAVEPOINT {savepoint}")
            else:
                conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                if nested:
                    conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                else:
                    conn.execute("ROLLBACK")
                raise
            else:
                if nested:
                    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                else:
                    conn.execute("COMMIT")
        finally:
            self._transaction_state.depth = depth
            self._transaction_lock.release()

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
