"""End-to-end tests for the quick-action route (ADR-0003 Phase F · v0.1.34)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from synapse_daemon import projects as projects_module
from synapse_daemon.app import build_app
from synapse_daemon.pty_sessions import PtySessionManager
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX PTY only in tests"
)


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, storage, app


# ── list ─────────────────────────────────────────────────────────────────


def test_list_quick_actions_returns_bundled_templates(tmp_path: Path) -> None:
    client, _, _ = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/quick-actions")
    assert res.status_code == 200, res.text
    body = res.json()
    ids = [a["id"] for a in body["actions"]]
    assert "new-mcp-server" in ids
    assert "new-synapse-tool" in ids
    # Each action exposes the prompt directly so the renderer can preview it.
    for a in body["actions"]:
        assert a["prompt"].strip()
        assert isinstance(a["category"], str) and a["category"]
        assert isinstance(a["tags"], list) and a["tags"]


def test_list_quick_actions_requires_auth(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    unauthed = TestClient(app)
    assert unauthed.get("/api/v1/quick-actions").status_code == 401


# ── launch (mocked spawn so it works on Windows too) ─────────────────────


@dataclass
class _FakeSession:
    session_id: str
    pid: int = 4242
    cwd: str = ""
    argv: tuple = ()

    def summary(self) -> Any:
        @dataclass
        class _Summary:
            session_id: str
            pid: int
            cwd: str
            argv: list[str]

        return _Summary(self.session_id, self.pid, self.cwd, list(self.argv))


def test_launch_creates_scratch_project_and_drops_prompt_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, storage, _ = _harness(tmp_path)

    captured: dict[str, Any] = {}

    async def fake_spawn(self, *, argv, cwd, env=None, rows=24, cols=80, project_id=None):  # type: ignore[override]
        captured["argv"] = argv
        captured["cwd"] = cwd
        captured["env"] = env
        captured["project_id"] = project_id
        return _FakeSession(session_id="aaaaaa111111", cwd=cwd, argv=tuple(argv))

    monkeypatch.setattr(PtySessionManager, "spawn", fake_spawn)

    with client as c:
        res = c.post("/api/v1/quick-actions/new-mcp-server/launch")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["project_id"] == "scratch"
    assert body["action_id"] == "new-mcp-server"
    assert body["session_id"] == "aaaaaa111111"

    # The scratch project row was lazily created.
    scratch = projects_module.get_or_none(storage.conn, "scratch")
    assert scratch is not None
    assert scratch.name == "Quick-action scratchpad"

    # The prompt file was written to the scratch project's cwd.
    prompt_file = Path(body["prompt_file"])
    assert prompt_file.exists()
    contents = prompt_file.read_text(encoding="utf-8")
    assert "MCP" in contents or "Model Context Protocol" in contents
    # PROMPT.md mirror is in place so AI sessions can rely on the stable name.
    assert (Path(scratch.path) / "PROMPT.md").exists()

    # The PTY environment carries the prompt for any AI session that wants it.
    assert captured["env"]["SYNAPSE_QUICK_ACTION_ID"] == "new-mcp-server"
    assert "MCP" in captured["env"]["SYNAPSE_QUICK_ACTION_PROMPT"]
    assert captured["project_id"] == "scratch"


def test_launch_unknown_action_is_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, _ = _harness(tmp_path)

    async def fake_spawn(self, **_kw):
        raise AssertionError("spawn should never be reached on a 404 action")

    monkeypatch.setattr(PtySessionManager, "spawn", fake_spawn)

    with client as c:
        res = c.post("/api/v1/quick-actions/does-not-exist/launch")
    assert res.status_code == 404
    assert res.json()["code"].startswith("quick_action.")


def test_launch_propagates_missing_binary_as_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, _ = _harness(tmp_path)

    async def fake_spawn(self, **_kw):
        raise FileNotFoundError("command not found on PATH: 'claude'")

    monkeypatch.setattr(PtySessionManager, "spawn", fake_spawn)

    with client as c:
        res = c.post("/api/v1/quick-actions/new-mcp-server/launch")
    assert res.status_code == 422
    assert "claude" in res.json()["message"]


def test_launch_reuses_existing_scratch_project_across_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, storage, _ = _harness(tmp_path)

    calls: list[str] = []

    async def fake_spawn(self, *, argv, cwd, env=None, rows=24, cols=80, project_id=None):  # type: ignore[override]
        calls.append(project_id or "")
        return _FakeSession(session_id=f"sid-{len(calls):06x}", cwd=cwd, argv=tuple(argv))

    monkeypatch.setattr(PtySessionManager, "spawn", fake_spawn)

    with client as c:
        a = c.post("/api/v1/quick-actions/new-mcp-server/launch")
        b = c.post("/api/v1/quick-actions/new-synapse-tool/launch")
    assert a.status_code == 200 and b.status_code == 200
    assert calls == ["scratch", "scratch"]
    # Only one project row was ever created.
    assert projects_module.get_or_none(storage.conn, "scratch") is not None
