"""Migration 026 rebuilds coder_threads with foreign_keys OFF so child history survives.

Regression guard for a data-loss bug: a table rebuild (DROP + RENAME) with foreign_keys ON
cascade-deletes coder_messages / coder_runs / coder_review_passes / coder_runtime_switches when the
parent coder_threads is dropped. The runner's ``runner:foreign_keys=off`` marker (+ foreign_key_check)
prevents that. On a fresh/empty DB the bug is invisible (no children to delete) -- this test
populates a child row BEFORE 026 to actually exercise it.
"""

from __future__ import annotations

from pathlib import Path

from synapse_daemon.migrations import list_migrations
from synapse_daemon.migrations._runner import apply_pending
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.storage import Storage


def test_migration_026_preserves_child_rows_on_populated_db(tmp_path: Path) -> None:
    s = Storage(tmp_path / "data")
    s.open()
    conn = s.conn
    migrations = list_migrations()
    now = "2026-07-08T00:00:00Z"

    # Apply everything BEFORE 026, then populate a project + thread + a child message.
    apply_pending(conn, [m for m in migrations if m.number < 26])
    with s.transaction() as c:
        create_project(c, Project(id="p1", name="P", path="/tmp", launch_cmd="echo hi"))
        c.execute(
            "INSERT INTO coder_threads (id,project_id,title,status,created_at,updated_at)"
            " VALUES ('t1','p1','T','active',?,?)",
            (now, now),
        )
        c.execute(
            "INSERT INTO coder_messages (id,thread_id,role,content_md,created_at)"
            " VALUES ('m1','t1','user','hi',?)",
            (now,),
        )
    assert conn.execute("SELECT COUNT(*) FROM coder_messages").fetchone()[0] == 1

    # Apply 026 (the rebuild). With foreign_keys ON this DROP TABLE would cascade-delete m1.
    applied = apply_pending(conn, migrations)
    assert 26 in applied

    # The child message survives and still points at its thread...
    assert conn.execute("SELECT COUNT(*) FROM coder_messages").fetchone()[0] == 1
    assert conn.execute("SELECT thread_id FROM coder_messages WHERE id='m1'").fetchone()[0] == "t1"
    # ...and project_id is now nullable (General scope is possible).
    conn.execute(
        "INSERT INTO coder_threads (id,project_id,title,status,created_at,updated_at)"
        " VALUES ('t2',NULL,'Gen','active',?,?)",
        (now, now),
    )
    assert conn.execute("SELECT project_id FROM coder_threads WHERE id='t2'").fetchone()[0] is None

    # FK enforcement was restored after the migration: ON DELETE SET NULL nulls the thread's project.
    conn.execute("DELETE FROM projects WHERE id='p1'")
    assert conn.execute("SELECT project_id FROM coder_threads WHERE id='t1'").fetchone()[0] is None
