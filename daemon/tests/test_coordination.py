"""Tests for native multi-AI coordination (ADR-0024).

Covers presence heartbeat + staleness, advisory file-lane claims + overlap
detection (the exact "two AIs edit the same file" scenario), the git
working-tree collision detector, disk-truth migration/ADR numbering, a bare-app
router E2E, and chaos cases (empty/malformed input, unknown ids).
"""

from __future__ import annotations

import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from synapse_daemon import coordination as coord
from synapse_daemon.errors import SynapseError
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.routes_coordination import build_coordination_router
from synapse_daemon.storage import Storage
from synapse_daemon.time_utils import to_iso, utc_now


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


def _register(conn, **kwargs) -> coord.AgentSession:
    return coord.register_session(conn, coord.AgentSessionRegister(**kwargs))


# -- presence -----------------------------------------------------------------


def test_register_heartbeat_and_list(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        session = _register(conn, runtime_id="claude", agent_label="Claude Opus 4.8", task="Phase A")
    assert session.status == coord.AgentSessionStatus.ACTIVE
    assert session.stale is False

    with storage.transaction() as conn:
        beat = coord.heartbeat_session(
            conn, session.id, coord.AgentSessionHeartbeat(status=coord.AgentSessionStatus.HOLDING)
        )
    assert beat.status == coord.AgentSessionStatus.HOLDING

    listed = coord.list_sessions(storage.conn)
    assert [s.id for s in listed] == [session.id]


def test_stale_session_is_flagged_then_expired(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        session = _register(conn, runtime_id="codex")
        # Backdate the heartbeat well past the stale window.
        old = to_iso(utc_now() - timedelta(seconds=coord.SESSION_STALE_SECONDS + 60))
        conn.execute(
            "UPDATE agent_sessions SET last_heartbeat_at = ? WHERE id = ?", (old, session.id)
        )

    flagged = coord.list_sessions(storage.conn)[0]
    assert flagged.stale is True
    assert flagged.status == coord.AgentSessionStatus.ACTIVE  # not yet swept

    with storage.transaction() as conn:
        expired = coord.expire_stale_sessions(conn)
    assert expired == 1
    # After the sweep it is 'gone' and excluded by default.
    assert coord.list_sessions(storage.conn) == []
    assert len(coord.list_sessions(storage.conn, include_gone=True)) == 1


def test_end_session_releases_its_active_lanes(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        session = _register(conn, runtime_id="claude")
        coord.claim_lane(conn, None, coord.LaneClaim(session_id=session.id, path_globs=["src/a.py"]))
    assert len(coord.list_active_lanes(storage.conn)) == 1

    with storage.transaction() as conn:
        coord.end_session(conn, session.id)
    assert coord.list_active_lanes(storage.conn) == []


# -- file lanes + overlap -----------------------------------------------------


def test_disjoint_claims_do_not_conflict(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        a = _register(conn, runtime_id="claude")
        b = _register(conn, runtime_id="codex")
        coord.claim_lane(conn, None, coord.LaneClaim(session_id=a.id, path_globs=["renderer/**"]))
        result = coord.claim_lane(
            conn, None, coord.LaneClaim(session_id=b.id, path_globs=["daemon/**"])
        )
    assert result.granted is True
    assert result.conflicts == []


def test_overlapping_claim_returns_conflict(tmp_path: Path) -> None:
    """The exact pain this feature automates: two agents claim the same file."""
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        claude = _register(conn, runtime_id="claude", agent_label="Claude")
        codex = _register(conn, runtime_id="codex", agent_label="Codex")
        coord.claim_lane(
            conn,
            None,
            coord.LaneClaim(
                session_id=codex.id,
                path_globs=["daemon/synapse_daemon/routes_coder_workspace.py"],
                task_ref="reviewer presets",
            ),
        )
        result = coord.claim_lane(
            conn,
            None,
            coord.LaneClaim(
                session_id=claude.id,
                path_globs=["daemon/synapse_daemon/routes_coder_workspace.py"],
                task_ref="Phase A",
            ),
        )
    assert result.granted is True  # advisory -- always granted
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.owner_label == "Codex"
    assert "daemon/synapse_daemon/routes_coder_workspace.py" in conflict.overlapping


def test_release_lane_removes_it_from_active(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        session = _register(conn, runtime_id="claude")
        result = coord.claim_lane(
            conn, None, coord.LaneClaim(session_id=session.id, path_globs=["a.py"])
        )
        lane_id = result.lane.id
    with storage.transaction() as conn:
        released = coord.release_lane(conn, lane_id)
    assert released.status == coord.FileLaneStatus.RELEASED
    assert coord.list_active_lanes(storage.conn) == []


def test_glob_overlap_matching_rules() -> None:
    assert coord._one_overlap("a/b.py", "a/b.py") is True  # exact
    assert coord._one_overlap("a/b.py", "a/*.py") is True  # fnmatch
    assert coord._one_overlap("renderer", "renderer/pages/X.tsx") is True  # dir prefix
    assert coord._one_overlap("a\\b.py", "a/b.py") is True  # backslash normalise
    assert coord._one_overlap("a/b.py", "a/c.py") is False  # disjoint
    assert coord._globs_overlap(["src/**"], ["src/x.py", "docs/y.md"]) == ["src/x.py"]


def test_repo_scope_isolated_from_project_scope(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        create_project(conn, Project(id="p1", name="P1", path=str(tmp_path), launch_cmd="echo"))
        repo_sess = _register(conn, runtime_id="claude")  # project_id None
        proj_sess = _register(conn, runtime_id="codex", project_id="p1")
        coord.claim_lane(conn, None, coord.LaneClaim(session_id=repo_sess.id, path_globs=["a.py"]))
        # Same path, but claimed in the 'p1' project scope -> no cross-scope conflict.
        result = coord.claim_lane(
            conn, "p1", coord.LaneClaim(session_id=proj_sess.id, path_globs=["a.py"])
        )
    assert result.conflicts == []
    assert len(coord.list_active_lanes(storage.conn, None)) == 1
    assert len(coord.list_active_lanes(storage.conn, "p1")) == 1


# -- collision detector -------------------------------------------------------


def test_detect_collisions_flags_dirty_file_in_lane(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    repo = tmp_path / "repo"
    (repo / "daemon").mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=False)
    (repo / "daemon" / "x.py").write_text("print('hi')\n", encoding="utf-8")  # untracked -> dirty

    with storage.transaction() as conn:
        session = _register(conn, runtime_id="claude", agent_label="Claude")
        coord.claim_lane(conn, None, coord.LaneClaim(session_id=session.id, path_globs=["daemon/*.py"]))

    hits = coord.detect_collisions(storage.conn, None, repo)
    assert any(h.path == "daemon/x.py" and h.owner_label == "Claude" for h in hits)


def test_parse_git_status_handles_renames_and_untracked() -> None:
    out = " M daemon/a.py\n?? new.txt\nR  old.py -> renamed.py\n"
    assert coord._parse_git_status(out) == ["daemon/a.py", "new.txt", "renamed.py"]
    assert coord._parse_git_status("") == []


# -- disk-truth numbering -----------------------------------------------------


def test_next_numbers_scan_disk(tmp_path: Path) -> None:
    mig = tmp_path / "daemon" / "synapse_daemon" / "migrations"
    mig.mkdir(parents=True)
    (mig / "001_a.sql").write_text("", encoding="utf-8")
    (mig / "019_quality_os.sql").write_text("", encoding="utf-8")
    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "0001-x.md").write_text("", encoding="utf-8")
    (adr / "0023-y.md").write_text("", encoding="utf-8")
    (adr / "README.md").write_text("", encoding="utf-8")  # ignored (no number)

    assert coord.next_migration_number(tmp_path) == 20
    assert coord.next_adr_number(tmp_path) == 24


# -- chaos --------------------------------------------------------------------


def test_claim_requires_at_least_one_glob(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        session = _register(conn, runtime_id="claude")
        with pytest.raises(SynapseError):
            coord.claim_lane(conn, None, coord.LaneClaim(session_id=session.id, path_globs=[]))


def test_claim_with_unknown_session_raises_not_found(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        with pytest.raises(SynapseError):
            coord.claim_lane(conn, None, coord.LaneClaim(session_id="nope", path_globs=["a.py"]))


def test_detect_overlap_empty_paths_is_empty(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    assert coord.detect_overlap(storage.conn, None, []) == []


# -- router E2E (bare app, no app.py needed) ----------------------------------


def _client(storage: Storage) -> TestClient:
    app = FastAPI()

    async def _synapse_error_handler(_request, exc: SynapseError):
        return JSONResponse(status_code=exc.status, content=exc.envelope.model_dump())

    app.add_exception_handler(SynapseError, _synapse_error_handler)
    app.include_router(build_coordination_router(storage), prefix="/api/v1")
    return TestClient(app)


def test_router_register_claim_and_conflict(tmp_path: Path) -> None:
    client = _client(_storage(tmp_path))

    r1 = client.post("/api/v1/coordination/sessions", json={"runtime_id": "codex", "agent_label": "Codex"})
    assert r1.status_code == 200
    codex_id = r1.json()["id"]

    r2 = client.post("/api/v1/coordination/sessions", json={"runtime_id": "claude", "agent_label": "Claude"})
    claude_id = r2.json()["id"]

    # Codex claims a file.
    c1 = client.post(
        "/api/v1/coordination/lanes",
        json={"session_id": codex_id, "path_globs": ["renderer/pages/CoderWorkspace.tsx"]},
    )
    assert c1.status_code == 200
    assert c1.json()["conflicts"] == []

    # Claude claims the same file -> advisory conflict surfaced.
    c2 = client.post(
        "/api/v1/coordination/lanes",
        json={"session_id": claude_id, "path_globs": ["renderer/pages/CoderWorkspace.tsx"]},
    )
    body = c2.json()
    assert body["granted"] is True
    assert len(body["conflicts"]) == 1
    assert body["conflicts"][0]["owner_label"] == "Codex"

    # Snapshot shows both sessions + both lanes.
    snap = client.get("/api/v1/coordination/snapshot").json()
    assert len(snap["sessions"]) == 2
    assert len(snap["lanes"]) == 2


def test_router_next_numbers_and_overlap_and_invalid(tmp_path: Path) -> None:
    client = _client(_storage(tmp_path))

    nums = client.get("/api/v1/coordination/next-numbers").json()
    assert isinstance(nums["migration"], int) and nums["migration"] >= 1
    assert isinstance(nums["adr"], int) and nums["adr"] >= 1

    reg = client.post("/api/v1/coordination/sessions", json={"runtime_id": "claude"})
    sid = reg.json()["id"]
    client.post(
        "/api/v1/coordination/lanes",
        json={"session_id": sid, "path_globs": ["daemon/synapse_daemon/app.py"]},
    )
    # A different agent's staged file overlaps -> reported by /overlap.
    ov = client.post(
        "/api/v1/coordination/overlap",
        json={"paths": ["daemon/synapse_daemon/app.py"], "project_id": None},
    ).json()
    assert ov["has_conflicts"] is True

    # Empty globs -> 422 invalid envelope.
    bad = client.post("/api/v1/coordination/lanes", json={"session_id": sid, "path_globs": []})
    assert bad.status_code == 422
