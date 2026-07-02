from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from synapse_daemon import ai_bundles
from synapse_daemon.app import build_app
from synapse_daemon.projects import list_projects
from synapse_daemon.storage import Storage
from synapse_daemon.tools_registry import ToolRegistry
from synapse_daemon.ws import EventBus
from synapse_daemon.tools import fast_money as fast_money_module

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FAST_MONEY_MANIFEST = json.loads(
    (_REPO_ROOT / "tools" / "fast-money" / "manifest.json").read_text(encoding="utf-8")
)


def _harness(tmp_path: Path) -> tuple[object, TestClient, Storage]:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    bus = EventBus()

    tools_dir = tmp_path / "tools"
    tool_dir = tools_dir / "fast-money"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "manifest.json").write_text(
        json.dumps(_FAST_MONEY_MANIFEST),
        encoding="utf-8",
    )

    registry = ToolRegistry(tools_dir, bus, storage)
    registry.load()
    app = build_app(storage, bus, tool_registry=registry)
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return app, client, storage


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available: tuple[str, ...] = ("codex", "claude", "copilot"),
) -> None:
    def fake_resolve(command: str) -> str | None:
        if command in available:
            return f"C:/fake/{command}.exe"
        return None

    monkeypatch.setattr(fast_money_module, "resolve_command", fake_resolve)


def _patch_spawn(monkeypatch: pytest.MonkeyPatch, app) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    async def fake_spawn(
        *,
        argv,
        cwd,
        env=None,
        rows=24,
        cols=80,
        project_id=None,
        session_id=None,
    ):
        call = {
            "argv": list(argv),
            "cwd": cwd,
            "env": dict(env or {}),
            "rows": rows,
            "cols": cols,
            "project_id": project_id,
        }
        calls.append(call)
        sid = f"sid-{len(calls)}"

        class _Session:
            def summary(self):
                return SimpleNamespace(
                    session_id=sid,
                    pid=4512,
                    cwd=cwd,
                    argv=list(argv),
                    started_at="2026-06-28T00:00:00+00:00",
                    exit_code=None,
                    rows=rows,
                    cols=cols,
                    project_id=project_id,
                )

        return _Session()

    monkeypatch.setattr(app.state.pty_manager, "spawn", fake_spawn)
    return calls


def test_fast_money_launch_installs_bundle_and_creates_default_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, storage = _harness(tmp_path)
    _patch_runtime(monkeypatch, available=("codex",))
    spawn_calls = _patch_spawn(monkeypatch, app)

    with client as c:
        res = c.post("/api/v1/tools/fast-money/actions/launch")

    assert res.status_code == 200, res.text
    state = res.json()["state"]
    result = state["result"]
    expected_path = (storage.data_dir / "projects" / "fast-money-client-ops").resolve()

    assert state["status"] == "launched"
    assert result["bundle_id"] == "fast-money"
    assert result["chosen_runtime"] == "codex"
    assert result["project_id"] == "fast-money-client-ops"
    assert Path(result["project_path"]) == expected_path
    assert result["session_id"] == "sid-1"
    assert result["reference_app_created"] is True
    assert "fast-money" in ai_bundles.list_installed_bundle_ids(storage.conn)
    assert [project.id for project in list_projects(storage.conn)] == ["fast-money-client-ops"]
    assert expected_path.exists()
    assert spawn_calls[0]["project_id"] == "fast-money-client-ops"
    assert spawn_calls[0]["argv"] == ["codex"]
    assert spawn_calls[0]["cwd"] == str(expected_path)
    assert spawn_calls[0]["env"]["SYNAPSE_FAST_MONEY_BUNDLE_ID"] == "fast-money"


def test_fast_money_launch_reuses_existing_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, storage = _harness(tmp_path)
    _patch_runtime(monkeypatch, available=("codex",))
    _patch_spawn(monkeypatch, app)

    with client as c:
        first = c.post(
            "/api/v1/tools/fast-money/actions/launch",
            json={"fields": {"output_path": "custom-client-ops"}},
        )
        second = c.post(
            "/api/v1/tools/fast-money/actions/launch",
            json={"fields": {"output_path": "custom-client-ops"}},
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    first_result = first.json()["state"]["result"]
    second_result = second.json()["state"]["result"]
    assert first_result["project_id"] == second_result["project_id"]
    assert first_result["reference_app_created"] is True
    assert second_result["reference_app_created"] is False
    assert len(list_projects(storage.conn)) == 1


def test_fast_money_launch_writes_prompt_artifacts_and_scaffold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, storage = _harness(tmp_path)
    _patch_runtime(monkeypatch, available=("claude",))
    _patch_spawn(monkeypatch, app)

    with client as c:
        res = c.post(
            "/api/v1/tools/fast-money/actions/launch",
            json={
                "fields": {
                    "app_name": "Fast Money HVAC Ops",
                    "brief": "Build a private/local-first revenue workspace for HVAC operators.",
                    "pricing_model": "hybrid",
                    "include_catalog_editor": True,
                    "preferred_runtime": "claude",
                }
            },
        )

    assert res.status_code == 200, res.text
    result = res.json()["state"]["result"]
    project_path = Path(result["project_path"])
    brief = (project_path / "FAST_MONEY_BRIEF.md").read_text(encoding="utf-8")
    prompt = (project_path / "PROMPT.md").read_text(encoding="utf-8")
    config = json.loads((project_path / "fast_money.config.json").read_text(encoding="utf-8"))

    assert "Fast Money HVAC Ops" in brief
    assert "Lead -> quote -> approval -> engagement/job -> invoice -> renewal handoff" in brief
    assert "/api/v1/ai/context" in prompt
    assert "landing page" in prompt
    assert "billing and auth" in prompt.lower()
    assert config["include_catalog_editor"] is True
    assert config["pricing_model"] == "hybrid"
    assert (project_path / "README.md").exists()
    assert (project_path / "ARCHITECTURE.md").exists()
    assert (project_path / "MONETIZATION.md").exists()
    assert (project_path / "seed-data.json").exists()
    assert (project_path / "server.py").exists()
    assert (project_path / "static" / "styles.css").exists()
    assert (project_path / "static" / "app.js").exists()
    assert (storage.data_dir / "projects").exists()


def test_fast_money_launch_returns_clear_error_when_runtime_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app, client, storage = _harness(tmp_path)
    _patch_runtime(monkeypatch, available=())

    with client as c:
        res = c.post("/api/v1/tools/fast-money/actions/launch")

    assert res.status_code == 200, res.text
    state = res.json()["state"]
    assert state["status"] == "error"
    assert state["last_error"]["code"] == "fast-money.runtime_unavailable"
    assert "Install one of codex, claude, or copilot" in state["last_error"]["message"]
    assert ai_bundles.list_installed_bundle_ids(storage.conn) == []
    assert list_projects(storage.conn) == []
