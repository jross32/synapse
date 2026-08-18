"""The shared connection must survive concurrent transactions, not just sequential ones.

Reproduced for real: a background health probe held a transaction open across a network
`await`, and a concurrent `GET /profile` opening its own transaction collided with it -
`sqlite3.OperationalError: cannot start a transaction within a transaction`. Both the
specific bug (a transaction spanning a slow await) and the general one (the connection had
no protection against two callers doing that at once) are pinned here.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from synapse_daemon.storage import Storage


@pytest.fixture()
def storage(tmp_path):
    s = Storage(tmp_path)
    s.open()
    s.migrate()
    yield s
    s.close()


def test_two_threads_holding_transactions_at_once_do_not_crash(storage):
    """The exact shape of the real bug: one caller's transaction outlasts a slow step
    while a second caller opens its own at the same moment."""
    errors: list[Exception] = []
    started = threading.Event()

    def slow_writer():
        try:
            with storage.transaction() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
                conn.execute("INSERT INTO t (v) VALUES ('slow')")
                started.set()
                time.sleep(0.3)  # stands in for the network await that used to be here
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def concurrent_writer():
        started.wait(timeout=2)
        try:
            with storage.transaction() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
                conn.execute("INSERT INTO t (v) VALUES ('concurrent')")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=slow_writer), threading.Thread(target=concurrent_writer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors, f"a concurrent transaction crashed instead of waiting: {errors}"
    rows = storage.conn.execute("SELECT v FROM t ORDER BY v").fetchall()
    assert [r["v"] for r in rows] == ["concurrent", "slow"], (
        "both writers must have actually committed, not just avoided raising")


def test_ten_concurrent_transactions_all_commit(storage):
    """Not just two - a burst of callers must all serialize cleanly."""
    storage.conn.execute("CREATE TABLE counter (n INTEGER)")
    storage.conn.execute("INSERT INTO counter VALUES (0)")

    def bump():
        with storage.transaction() as conn:
            current = conn.execute("SELECT n FROM counter").fetchone()["n"]
            time.sleep(0.01)
            conn.execute("UPDATE counter SET n = ?", (current + 1,))

    threads = [threading.Thread(target=bump) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    final = storage.conn.execute("SELECT n FROM counter").fetchone()["n"]
    assert final == 10, (
        f"expected all ten increments to land, got {final} - a lost update means the lock "
        f"did not actually serialize the writers")


@pytest.mark.asyncio
async def test_a_transaction_spanning_an_await_no_longer_wedges_a_concurrent_caller(storage):
    """The scenario from process_manager._probe_health, reproduced against real asyncio.

    Before the fix this raised on the second `transaction()` call rather than waiting for
    the first to finish. It waiting instead of raising is the whole point.
    """
    storage.conn.execute("CREATE TABLE marker (name TEXT)")

    async def holds_across_an_await():
        with storage.transaction() as conn:
            conn.execute("INSERT INTO marker VALUES ('slow')")
            await asyncio.sleep(0.2)

    async def concurrent_request():
        await asyncio.sleep(0.05)  # let the first one open its transaction first
        await asyncio.to_thread(_write_marker, storage, "concurrent")

    await asyncio.gather(holds_across_an_await(), concurrent_request())

    names = {r["name"] for r in storage.conn.execute("SELECT name FROM marker")}
    assert names == {"slow", "concurrent"}


def _write_marker(storage: Storage, name: str) -> None:
    with storage.transaction() as conn:
        conn.execute("INSERT INTO marker VALUES (?)", (name,))
