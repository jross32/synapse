"""Tests for Sessions-centric AI squads."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon import agent_squads
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX PTY only in tests"
)


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="demo-project",
                name="Demo Project",
                path=str(tmp_path),
                launch_cmd="echo hi",
            ),
        )
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return app, client


def _create_squad(client: TestClient) -> dict:
    res = client.post(
        "/api/v1/agent-squads",
        json={
            "project_id": "demo-project",
            "name": "Release Squad",
            "goal_md": "Ship the feature and leave a clean handoff.",
            "lead_role_id": "planner",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _create_work_item(
    client: TestClient,
    squad_id: str,
    *,
    title: str = "Implement the feature",
    assigned_role_id: str = "implementer",
) -> dict:
    res = client.post(
        f"/api/v1/agent-squads/{squad_id}/work-items",
        json={
            "title": title,
            "instructions_md": "Make the change and run the check.",
            "assigned_role_id": assigned_role_id,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_pick_runtime_prefers_first_installed_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    role = agent_squads.AgentRoleTemplate(
        id="implementer",
        name="Implementer",
        preferred_runtimes=["codex", "claude", "copilot"],
    )

    # pick_runtime resolves candidates via runtime_resolution.resolve_command
    # (which looks beyond bare PATH -- e.g. the Codex VS Code extension), so
    # mock that, not shutil.which, to make the test machine-independent.
    monkeypatch.setattr(
        agent_squads,
        "resolve_command",
        lambda cmd: None if cmd == "codex" else f"/fake/{cmd}",
    )

    chosen = agent_squads.pick_runtime(role)
    assert chosen == "claude"


def test_delegate_creates_child_work_item_linked_by_parent_id(tmp_path: Path) -> None:
    app, client = _harness(tmp_path)
    with client as c:
        squad = _create_squad(c)
        parent = _create_work_item(c, squad["id"], assigned_role_id="planner")

        delegated = c.post(
            f"/api/v1/agent-work-items/{parent['id']}/delegate",
            json={
                "title": "Review the implementation",
                "instructions_md": "Read the diff and call out risks.",
                "assigned_role_id": "reviewer",
            },
        )
        assert delegated.status_code == 201, delegated.text
        child = delegated.json()
        assert child["parent_id"] == parent["id"]
        assert child["squad_id"] == squad["id"]
        detail = c.get(f"/api/v1/agent-squads/{squad['id']}").json()
        assert any(item["id"] == child["id"] for item in detail["work_items"])


def test_handoff_appends_to_project_ai_context_file(tmp_path: Path) -> None:
    app, client = _harness(tmp_path)
    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")

        handoff = c.post(
            f"/api/v1/agent-work-items/{item['id']}/handoff",
            json={
                "status": "handoff",
                "summary_md": "Added the route wiring and left UI follow-up.",
                "blockers_md": "Need a quick typecheck pass after the last refactor.",
                "files_touched": ["renderer/pages/Sessions.tsx", "daemon/synapse_daemon/app.py"],
                "suggested_next_role": "reviewer",
            },
        )
        assert handoff.status_code == 200, handoff.text
        body = handoff.json()
        assert body["status"] == "handoff"
        context_path = (
            tmp_path / "data" / "projects" / "demo-project" / ".synapse-ai-context.md"
        )
        assert context_path.exists()
        contents = context_path.read_text(encoding="utf-8")
        assert "Added the route wiring" in contents
        assert "renderer/pages/Sessions.tsx" in contents
        assert "Suggested next role" in contents


@posix_only
def test_launch_stores_session_and_injects_squad_env_vars(tmp_path: Path) -> None:
    app, client = _harness(tmp_path)
    script = tmp_path / "squad-env.sh"
    script.write_text("#!/usr/bin/env bash\nsleep 2\n", encoding="utf-8")
    script.chmod(0o755)

    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")

        launched = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={"preferred_runtime": str(script), "open_in_tab": False},
        )
        assert launched.status_code == 200, launched.text
        body = launched.json()
        assert body["work_item_id"] == item["id"]
        assert body["runtime"] == str(script)

        manager = app.state.pty_manager
        session = manager.get(body["session_id"])
        assert session is not None
        assert session._env["SYNAPSE_SQUAD_ID"] == squad["id"]  # noqa: SLF001
        assert session._env["SYNAPSE_WORK_ITEM_ID"] == item["id"]  # noqa: SLF001
        assert session._env["SYNAPSE_ROLE_ID"] == "implementer"  # noqa: SLF001
        assert session._env["SYNAPSE_LEAD_SESSION_ID"]  # noqa: SLF001
        assert session._env["SYNAPSE_ROLE_PROMPT_FILE"]  # noqa: SLF001

        detail = c.get(f"/api/v1/agent-squads/{squad['id']}").json()
        launched_item = next(entry for entry in detail["work_items"] if entry["id"] == item["id"])
        assert launched_item["pty_session_id"] == body["session_id"]
        assert launched_item["status"] == "running"
        c.delete(f"/api/v1/pty/{body['session_id']}")


@posix_only
def test_completed_work_item_links_transcript_after_session_exit(tmp_path: Path) -> None:
    app, client = _harness(tmp_path)
    script = tmp_path / "transcript.sh"
    script.write_text("#!/usr/bin/env bash\necho transcript-smoke\n", encoding="utf-8")
    script.chmod(0o755)

    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")

        launched = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={"preferred_runtime": str(script), "open_in_tab": False},
        )
        assert launched.status_code == 200, launched.text
        session_id = launched.json()["session_id"]

        for _ in range(40):
            detail = c.get(f"/api/v1/agent-squads/{squad['id']}").json()
            updated = next(entry for entry in detail["work_items"] if entry["id"] == item["id"])
            if updated["transcript_file_id"]:
                break
            time.sleep(0.1)
        else:
            pytest.fail("expected transcript_file_id to be linked after session exit")

        assert updated["status"] == "completed"
        assert updated["transcript_file_id"]
        files = c.get("/api/v1/projects/demo-project/files").json()["files"]
        transcript = next(file for file in files if file["id"] == updated["transcript_file_id"])
        assert transcript["source_session"] == session_id


def test_stop_squad_is_safe_when_idle(tmp_path: Path) -> None:
    app, client = _harness(tmp_path)
    with client as c:
        squad = _create_squad(c)
        _create_work_item(c, squad["id"])
        # Nothing launched -> the kill switch must still succeed cleanly so the
        # UI "Stop all" never errors on an idle squad.
        res = c.post(f"/api/v1/agent-squads/{squad['id']}/stop")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["squad_id"] == squad["id"]
        assert body["stopped_sessions"] == 0

        missing = c.post("/api/v1/agent-squads/does-not-exist/stop")
        assert missing.status_code >= 400
