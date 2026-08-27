"""Tests for Sessions-centric AI squads."""

from __future__ import annotations

import asyncio
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from synapse_daemon import agent_squads, chatgpt_child_agents, coordination, routes_agent_squads
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


def test_list_squad_work_items_returns_focused_collection(tmp_path: Path) -> None:
    _app, client = _harness(tmp_path)
    squad = _create_squad(client)
    first = _create_work_item(client, squad["id"], title="Review Live View")
    second = _create_work_item(client, squad["id"], title="Verify restart")

    response = client.get(f"/api/v1/agent-squads/{squad['id']}/work-items")

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["work_items"]] == [
        first["id"],
        second["id"],
    ]


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


def test_codex_work_item_launch_injects_enabled_mcp_servers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client = _harness(tmp_path)
    captured: dict[str, object] = {}

    async def _fake_spawn(**kwargs):
        captured.update(kwargs)
        reserved = app.state.storage.conn.execute(
            "SELECT id FROM ai_executions WHERE pty_session_id = ?", (kwargs["session_id"],)
        ).fetchone()
        linked = app.state.storage.conn.execute(
            "SELECT pty_session_id FROM agent_work_items WHERE id = ?", (env_item_id["id"],)
        ).fetchone()
        captured["reserved_before_spawn"] = bool(reserved)
        captured["linked_before_spawn"] = linked["pty_session_id"] if linked else None
        return SimpleNamespace(
            session_id=kwargs["session_id"],
            summary=lambda: SimpleNamespace(
                session_id=kwargs["session_id"],
                argv=kwargs["argv"],
                cwd=kwargs["cwd"],
                rows=kwargs["rows"],
                cols=kwargs["cols"],
                started_at="now",
                exit_code=None,
                alive=True,
                project_id=kwargs["project_id"],
            ),
        )

    env_item_id: dict[str, str] = {}
    monkeypatch.setattr(app.state.pty_manager, "spawn", _fake_spawn)
    monkeypatch.setattr(agent_squads, "resolve_command", lambda command: command)

    with client as c:
        reflex = c.post(
            "/api/v1/mcp-servers/install",
            json={
                "id": "reflex",
                "name": "Reflex",
                "transport": "stdio",
                "command": "node",
                "args": ["C:/reflex/mcp-server.js"],
                "env": {"SYNAPSE_TOKEN": "mcp-must-not-win"},
            },
        )
        assert reflex.status_code == 201, reflex.text
        github = c.post(
            "/api/v1/mcp-servers/install",
            json={
                "id": "github",
                "name": "GitHub",
                "transport": "stdio",
                "command": "npx",
                "env": {"GITHUB_TOKEN": "supersecret"},
            },
        )
        assert github.status_code == 201, github.text
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        env_item_id["id"] = item["id"]
        launched = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={"preferred_runtime": "codex", "open_in_tab": False},
        )
        assert launched.status_code == 200, launched.text

        worker_env = captured["env"]
        assert isinstance(worker_env, dict)
        worker_headers = {
            "X-Synapse-Token": worker_env["SYNAPSE_TOKEN"],
            "X-Synapse-Session": worker_env["SYNAPSE_SESSION_ID"],
        }
        assert c.get("/api/v1/projects", headers=worker_headers).status_code == 200
        denied_restart = c.post(
            "/api/v1/system/restart",
            headers=worker_headers,
            json={"operation_id": "worker-must-not-restart"},
        )
        assert denied_restart.status_code == 403
        assert denied_restart.json()["code"] == "auth.worker_scope_denied"
        other = c.post(
            "/api/v1/coordination/sessions",
            json={"runtime_id": "claude", "project_id": "demo-project"},
        ).json()
        denied_impersonation = c.patch(
            f"/api/v1/coordination/sessions/{other['id']}",
            headers=worker_headers,
            json={"agent_label": "Impersonated"},
        )
        assert denied_impersonation.status_code == 403

    argv = captured["argv"]
    env = captured["env"]
    assert isinstance(argv, list)
    assert isinstance(env, dict)
    assert captured["reserved_before_spawn"] is True
    assert captured["linked_before_spawn"] == captured["session_id"]
    assert "mcp_servers.reflex.command=\"node\"" in argv
    assert "mcp_servers.github.env_vars=[\"GITHUB_TOKEN\"]" in argv
    assert "supersecret" not in " ".join(argv)
    assert env["GITHUB_TOKEN"] == "supersecret"
    assert env["SYNAPSE_TOKEN"] != app.state.auth.local_token
    assert env["SYNAPSE_TOKEN"] == env["SYNAPSE_SESSION_KEY"]
    assert env["SYNAPSE_SESSION_ID"]
    subject = app.state.auth.subject_for_token(env["SYNAPSE_TOKEN"])
    assert subject is not None and subject.kind == "worker"
    assert subject.work_item_id == item["id"]


def test_launch_releases_storage_transaction_before_awaited_pty_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client = _harness(tmp_path)

    async def _fake_spawn(**kwargs):
        # This is the transaction a heartbeat, audit projection, or another
        # request may need while platform PTY startup is awaiting. Holding the
        # launch transaction here reproduces SQLite's nested-BEGIN failure.
        with app.state.storage.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value_json, updated_at) "
                "VALUES (?, ?, ?)",
                ("spawn-heartbeat-proof", 'true', "2026-08-01T00:00:00+00:00"),
            )
        await asyncio.sleep(0)
        return SimpleNamespace(
            session_id=kwargs["session_id"],
            exit_code=None,
            summary=lambda: SimpleNamespace(
                session_id=kwargs["session_id"],
                argv=kwargs["argv"],
                cwd=kwargs["cwd"],
                rows=kwargs["rows"],
                cols=kwargs["cols"],
                started_at="now",
                exit_code=None,
                alive=True,
                project_id=kwargs["project_id"],
            ),
        )

    monkeypatch.setattr(app.state.pty_manager, "spawn", _fake_spawn)
    monkeypatch.setattr(agent_squads, "resolve_command", lambda command: command)

    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        response = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={"preferred_runtime": "codex", "open_in_tab": False},
        )

    assert response.status_code == 200, response.text
    saved = app.state.storage.conn.execute(
        "SELECT value_json FROM settings WHERE key = 'spawn-heartbeat-proof'"
    ).fetchone()
    assert saved is not None and saved["value_json"] == "true"


def test_parallel_launch_requests_are_serialized_without_internal_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client = _harness(tmp_path)
    active_spawns = 0
    max_active_spawns = 0

    async def _fake_spawn(**kwargs):
        nonlocal active_spawns, max_active_spawns
        active_spawns += 1
        max_active_spawns = max(max_active_spawns, active_spawns)
        try:
            await asyncio.sleep(0.05)
            return SimpleNamespace(
                session_id=kwargs["session_id"],
                exit_code=None,
                summary=lambda: SimpleNamespace(
                    session_id=kwargs["session_id"],
                    argv=kwargs["argv"],
                    cwd=kwargs["cwd"],
                    rows=kwargs["rows"],
                    cols=kwargs["cols"],
                    started_at="now",
                    exit_code=None,
                    alive=True,
                    project_id=kwargs["project_id"],
                ),
            )
        finally:
            active_spawns -= 1

    monkeypatch.setattr(app.state.pty_manager, "spawn", _fake_spawn)
    monkeypatch.setattr(agent_squads, "resolve_command", lambda command: command)

    with client as c:
        squad = _create_squad(c)
        items = [
            _create_work_item(c, squad["id"], title=f"Worker {index}")
            for index in range(2)
        ]

        def _launch(item: dict) -> tuple[int, str]:
            response = c.post(
                f"/api/v1/agent-work-items/{item['id']}/launch",
                json={"preferred_runtime": "codex", "open_in_tab": False},
            )
            return response.status_code, response.text

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(_launch, items))

    assert [status for status, _ in results] == [200, 200], results
    assert max_active_spawns == 1


def test_spawn_failure_releases_preregistered_worker_presence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client = _harness(tmp_path)

    async def _fail_spawn(**kwargs):
        raise RuntimeError("simulated PTY startup failure")

    monkeypatch.setattr(app.state.pty_manager, "spawn", _fail_spawn)
    monkeypatch.setattr(agent_squads, "resolve_command", lambda command: command)

    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        response = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={"preferred_runtime": "codex", "open_in_tab": False},
        )
        detail = c.get(f"/api/v1/agent-squads/{squad['id']}").json()

    assert response.status_code == 422, response.text
    updated = next(entry for entry in detail["work_items"] if entry["id"] == item["id"])
    assert updated["status"] == "queued"
    worker_sessions = [
        session
        for session in routes_agent_squads.coordination.list_all_sessions(app.state.storage.conn)
        if session.task == item["title"]
    ]
    assert len(worker_sessions) == 1
    assert worker_sessions[0].status.value == "gone"


def test_copilot_work_item_launch_injects_session_only_mcp_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client = _harness(tmp_path)
    captured: dict[str, object] = {}

    async def _fake_spawn(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            session_id=kwargs["session_id"],
            summary=lambda: SimpleNamespace(
                session_id=kwargs["session_id"],
                argv=kwargs["argv"],
                cwd=kwargs["cwd"],
                rows=kwargs["rows"],
                cols=kwargs["cols"],
                started_at="now",
                exit_code=None,
                alive=True,
                project_id=kwargs["project_id"],
            ),
        )

    monkeypatch.setattr(app.state.pty_manager, "spawn", _fake_spawn)
    monkeypatch.setattr(agent_squads, "resolve_command", lambda command: command)

    with client as c:
        installed = c.post(
            "/api/v1/mcp-servers/install",
            json={
                "id": "reflex",
                "name": "Reflex",
                "transport": "stdio",
                "command": "node",
                "args": ["C:/reflex/mcp-server.js"],
                "env": {"REFLEX_AGENT_NAME": "Copilot Worker"},
            },
        )
        assert installed.status_code == 201, installed.text
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        launched = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={"preferred_runtime": "copilot", "open_in_tab": False},
        )
        assert launched.status_code == 200, launched.text

    argv = captured["argv"]
    env = captured["env"]
    assert isinstance(argv, list)
    assert isinstance(env, dict)
    config_arg = next(value for value in argv if value.startswith("--additional-mcp-config=@"))
    config_path = Path(config_arg.split("@", 1)[1])
    config_text = config_path.read_text(encoding="utf-8")
    assert "${REFLEX_AGENT_NAME}" in config_text
    assert "Copilot Worker" not in config_text
    assert env["REFLEX_AGENT_NAME"] == "Copilot Worker"


@pytest.mark.parametrize(
    ("runtime", "authority", "expected"),
    [
        ("claude", agent_squads.AgentExecutionAuthority.WORKSPACE, ["--print", "--strict-mcp-config"]),
        # `--ignore-user-config` was removed in 0.1.149: it silently overrides
        # `--sandbox workspace-write` back to read-only, so codex refused every patch and
        # exited 0 - every squad worker on this runtime had been unable to write a file.
        # The sandbox flag is what WORKSPACE authority actually means here, so assert that.
        ("codex", agent_squads.AgentExecutionAuthority.WORKSPACE,
         ["exec", "--sandbox", "workspace-write"]),
        ("copilot", agent_squads.AgentExecutionAuthority.WORKSPACE, ["--prompt", "--no-ask-user"]),
    ],
)
def test_automatic_worker_argv_executes_prompt_with_explicit_authority(
    tmp_path: Path,
    runtime: str,
    authority: agent_squads.AgentExecutionAuthority,
    expected: list[str],
) -> None:
    prompt_file = (tmp_path / "role prompt.md").resolve()
    argv = routes_agent_squads._automatic_worker_argv(  # noqa: SLF001
        [runtime, "--runtime-config"],
        runtime=runtime,
        authority=authority,
        prompt_file=prompt_file,
    )

    assert all(value in argv for value in expected)
    assert str(prompt_file) in argv[-1]
    assert "explicit handoff" in argv[-1]


def test_full_authority_codex_automatic_launch_explicitly_ignores_exec_rules(tmp_path: Path) -> None:
    argv = routes_agent_squads._automatic_worker_argv(  # noqa: SLF001
        ["codex"],
        runtime="codex",
        authority=agent_squads.AgentExecutionAuthority.FULL,
        prompt_file=(tmp_path / "prompt.md").resolve(),
    )

    assert "--dangerously-bypass-approvals-and-sandbox" in argv
    assert "--ignore-rules" in argv


def test_workspace_claude_automatic_launch_uses_noninteractive_auto_permissions(tmp_path: Path) -> None:
    argv = routes_agent_squads._automatic_worker_argv(  # noqa: SLF001
        ["claude"],
        runtime="claude",
        authority=agent_squads.AgentExecutionAuthority.WORKSPACE,
        prompt_file=(tmp_path / "prompt.md").resolve(),
    )

    permission_index = argv.index("--permission-mode")
    assert argv[permission_index + 1] == "auto"


def test_observe_claude_worker_can_still_file_its_handoff(tmp_path: Path) -> None:
    """An observe worker must be able to complete its reporting contract.

    Regression for the real failure: two post-work council reviewers launched with
    observe authority ran under `--permission-mode plan`. Plan mode exists to withhold
    action until a human approves a plan, so one finished its entire review and then
    refused to POST the handoff -- the finding survived only inside a transcript -- and
    the other produced nothing before its deadline. The worker's own prompt requires the
    handoff, so the mode and the contract were in direct conflict.
    """
    argv = routes_agent_squads._automatic_worker_argv(  # noqa: SLF001
        ["claude"],
        runtime="claude",
        authority=agent_squads.AgentExecutionAuthority.OBSERVE,
        prompt_file=(tmp_path / "prompt.md").resolve(),
    )

    assert "plan" not in argv, "plan mode cannot post a handoff; that is the bug"
    permission_index = argv.index("--permission-mode")
    assert argv[permission_index + 1] == "auto"
    # The prompt still demands the handoff, so the two must stay compatible.
    assert "explicit handoff" in argv[-1]


def test_observe_claude_worker_still_cannot_mutate_files(tmp_path: Path) -> None:
    """Moving off plan mode must not quietly turn observe into write access."""
    argv = routes_agent_squads._automatic_worker_argv(  # noqa: SLF001
        ["claude"],
        runtime="claude",
        authority=agent_squads.AgentExecutionAuthority.OBSERVE,
        prompt_file=(tmp_path / "prompt.md").resolve(),
    )

    denied_index = argv.index("--disallowedTools")
    denied = argv[denied_index + 1].split()
    assert {"Write", "Edit", "NotebookEdit"} <= set(denied)
    # Workspace authority is the level that may edit -- it must NOT inherit the denial.
    workspace_argv = routes_agent_squads._automatic_worker_argv(  # noqa: SLF001
        ["claude"],
        runtime="claude",
        authority=agent_squads.AgentExecutionAuthority.WORKSPACE,
        prompt_file=(tmp_path / "prompt.md").resolve(),
    )
    assert "--disallowedTools" not in workspace_argv


def test_observe_codex_worker_keeps_its_real_sandbox(tmp_path: Path) -> None:
    """Codex's observe boundary is an OS sandbox and must be left intact.

    Guards the asymmetry: relaxing Claude's observe mode says nothing about Codex,
    which has a genuine `--sandbox read-only` and should keep it.
    """
    argv = routes_agent_squads._automatic_worker_argv(  # noqa: SLF001
        ["codex"],
        runtime="codex",
        authority=agent_squads.AgentExecutionAuthority.OBSERVE,
        prompt_file=(tmp_path / "prompt.md").resolve(),
    )

    sandbox_index = argv.index("--sandbox")
    assert argv[sandbox_index + 1] == "read-only"


def test_handoff_request_strips_terminal_control_characters() -> None:
    payload = agent_squads.AgentWorkItemHandoffRequest(
        summary_md="Reflex\x07 attached\nVerified",
        blockers_md="No\x1b blocker",
    )

    assert payload.summary_md == "Reflex attached\nVerified"
    assert payload.blockers_md == "No blocker"


def test_classify_worker_failure_turns_expired_claude_token_into_actionable_blocker() -> None:
    raw = b"Failed to authenticate. API Error: 401 OAuth access token has expired. Re-authenticate to continue."

    reason = agent_squads.classify_worker_failure(raw)

    assert reason is not None
    assert "Claude sign-in expired" in reason
    assert "claude auth login --claudeai" in reason
    assert "401" not in reason


def test_classify_worker_failure_turns_codex_usage_limit_into_actionable_blocker() -> None:
    raw = (
        b"ERROR: You've hit your usage limit. Visit "
        b"https://chatgpt.com/codex/settings/usage or try again later."
    )

    reason = agent_squads.classify_worker_failure(raw)

    assert reason is not None
    assert "Codex usage is temporarily exhausted" in reason
    assert "Settings" in reason
    assert "https://" not in reason


def test_automatic_launch_uses_absolute_prompt_and_mcp_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client = _harness(tmp_path)
    captured: dict[str, object] = {}

    async def _fake_spawn(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            session_id=kwargs["session_id"],
            exit_code=None,
            summary=lambda: SimpleNamespace(
                session_id=kwargs["session_id"],
                argv=kwargs["argv"],
                cwd=kwargs["cwd"],
                rows=kwargs["rows"],
                cols=kwargs["cols"],
                started_at="now",
                exit_code=None,
                alive=True,
                project_id=kwargs["project_id"],
            ),
        )

    monkeypatch.setattr(app.state.pty_manager, "spawn", _fake_spawn)
    monkeypatch.setattr(agent_squads, "resolve_command", lambda command: command)

    with client as c:
        installed = c.post(
            "/api/v1/mcp-servers/install",
            json={
                "id": "reflex",
                "name": "Reflex",
                "transport": "stdio",
                "command": "node",
                "args": ["C:/reflex/mcp-server.js"],
            },
        )
        assert installed.status_code == 201, installed.text
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        launched = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={
                "preferred_runtime": "codex",
                "open_in_tab": False,
                "execution_mode": "automatic",
                "authority": "workspace",
                "timeout_seconds": 600,
                "env": {
                    "SYNAPSE_TOKEN": "caller-must-not-win",
                    "SYNAPSE_ROLE_PROMPT_FILE": "C:/caller/prompt.md",
                },
            },
        )
        assert launched.status_code == 200, launched.text
        body = launched.json()
        assert body["execution_id"]

    argv = captured["argv"]
    env = captured["env"]
    assert isinstance(argv, list)
    assert isinstance(env, dict)
    assert argv[1] == "exec"
    assert body["execution_mode"] == "automatic"
    assert body["authority"] == "workspace"
    assert Path(env["SYNAPSE_ROLE_PROMPT_FILE"]).is_absolute()
    assert Path(env["SYNAPSE_AI_CONTEXT"]).is_absolute()
    assert env["SYNAPSE_API"] == "http://127.0.0.1:7878/api/v1"
    assert env["SYNAPSE_TOKEN"] != app.state.auth.local_token
    assert env["SYNAPSE_TOKEN"] == env["SYNAPSE_SESSION_KEY"]
    assert env["SYNAPSE_PROJECT_ID"] == "demo-project"
    assert env["SYNAPSE_RUNTIME_ID"] == "codex"
    assert env["SYNAPSE_PTY_SESSION_ID"]
    assert env["SYNAPSE_SESSION_ID"] == body["coordination_session_id"]
    assert env["SYNAPSE_ROLE_PROMPT_FILE"] != "C:/caller/prompt.md"
    assert str(Path(env["SYNAPSE_ROLE_PROMPT_FILE"])) in argv[-1]
    execution = app.state.storage.conn.execute(
        "SELECT * FROM ai_executions WHERE id = ?", (body["execution_id"],)
    ).fetchone()
    assert execution is not None
    assert execution["source_id"] == item["id"]
    assert execution["pty_session_id"] == body["session_id"]
    assert execution["runtime_id"] == "codex"
    assert execution["authority"] == "workspace"
    with app.state.storage.transaction() as conn:
        from synapse_daemon import ai_executions
        ai_executions.finalize_pty_execution(
            conn,
            pty_session_id=body["session_id"],
            output=b"tokens used: 49,912",
            exit_code=0,
            work_outcome="handoff",
        )
    with client as c:
        usage = c.get(f"/api/v1/agent-work-items/{item['id']}/tokens").json()
        assert len(usage) == 1
        assert usage[0]["total_tokens"] == 49_912
        assert usage[0]["token_provenance"] == "runtime_reported"
        rollup = c.get(f"/api/v1/agent-squads/{squad['id']}/token-usage").json()
        assert rollup["total_tokens"] == 49_912


def test_role_default_execution_mode_is_used_when_launch_does_not_specify_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0025's load-bearing gap: PTY workers report zero tokens because nothing opts
    them into automatic mode by default. A role can now do that itself."""
    app, client = _harness(tmp_path)
    captured: dict[str, object] = {}

    async def _fake_spawn(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            session_id=kwargs["session_id"],
            exit_code=None,
            summary=lambda: SimpleNamespace(
                session_id=kwargs["session_id"],
                argv=kwargs["argv"],
                cwd=kwargs["cwd"],
                rows=kwargs["rows"],
                cols=kwargs["cols"],
                started_at="now",
                exit_code=None,
                alive=True,
                project_id=kwargs["project_id"],
            ),
        )

    monkeypatch.setattr(app.state.pty_manager, "spawn", _fake_spawn)
    monkeypatch.setattr(agent_squads, "resolve_command", lambda command: command)

    with client as c:
        role = c.patch(
            "/api/v1/agent-role-templates/implementer",
            json={"default_execution_mode": "automatic"},
        )
        assert role.status_code == 200, role.text
        assert role.json()["default_execution_mode"] == "automatic"

        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        # No execution_mode in the launch payload -- the role's default must supply it.
        launched = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={"preferred_runtime": "codex", "open_in_tab": False},
        )
        assert launched.status_code == 200, launched.text
        body = launched.json()

    assert body["execution_mode"] == "automatic", (
        "the role's default_execution_mode should have been used since the launch "
        "request didn't specify one")
    assert captured["argv"][1] == "exec", (
        "automatic mode should have reached the spawned argv, not just the response body")


def test_explicit_launch_request_overrides_the_role_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client = _harness(tmp_path)
    captured: dict[str, object] = {}

    async def _fake_spawn(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            session_id=kwargs["session_id"],
            exit_code=None,
            summary=lambda: SimpleNamespace(
                session_id=kwargs["session_id"], argv=kwargs["argv"], cwd=kwargs["cwd"],
                rows=kwargs["rows"], cols=kwargs["cols"], started_at="now",
                exit_code=None, alive=True, project_id=kwargs["project_id"],
            ),
        )

    monkeypatch.setattr(app.state.pty_manager, "spawn", _fake_spawn)
    monkeypatch.setattr(agent_squads, "resolve_command", lambda command: command)

    with client as c:
        role = c.patch(
            "/api/v1/agent-role-templates/implementer",
            json={"default_execution_mode": "automatic"},
        )
        assert role.status_code == 200, role.text

        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        # Explicit "interactive" in the request must win over the role's "automatic" default.
        launched = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={"preferred_runtime": "codex", "open_in_tab": False,
                  "execution_mode": "interactive"},
        )
        assert launched.status_code == 200, launched.text
        body = launched.json()

    assert body["execution_mode"] == "interactive"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("starting_status", "expected_status", "expects_update"),
    [
        (agent_squads.AgentWorkItemStatus.RUNNING, "blocked", True),
        (agent_squads.AgentWorkItemStatus.HANDOFF, "handoff", False),
    ],
)
async def test_timeout_closes_live_worker_and_preserves_existing_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    starting_status: agent_squads.AgentWorkItemStatus,
    expected_status: str,
    expects_update: bool,
) -> None:
    app, client = _harness(tmp_path)
    closed: list[str] = []
    published: list[str] = []

    class StubBus:
        async def publish(self, name: str, payload: dict) -> None:
            published.append(name)

    async def _fake_close(session_id: str) -> bool:
        closed.append(session_id)
        return True

    monkeypatch.setattr(app.state.pty_manager, "get", lambda session_id: SimpleNamespace(exit_code=None))
    monkeypatch.setattr(app.state.pty_manager, "close", _fake_close)

    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        with app.state.storage.transaction() as conn:
            agent_squads.set_work_item_session(
                conn,
                item["id"],
                status=agent_squads.AgentWorkItemStatus.RUNNING,
                pty_session_id="deadline-session",
                chosen_runtime="codex",
                opened_in_tab=False,
            )
            if starting_status != agent_squads.AgentWorkItemStatus.RUNNING:
                agent_squads.update_work_item_status(conn, item["id"], starting_status)

        updated = await routes_agent_squads._close_worker_at_timeout(  # noqa: SLF001
            app.state.storage,
            app.state.pty_manager,
            StubBus(),  # type: ignore[arg-type]
            work_item_id=item["id"],
            session_id="deadline-session",
            timeout_seconds=30,
        )

    assert updated is not None
    assert updated.status.value == expected_status
    assert closed == ["deadline-session"]
    assert bool(published) is expects_update


@pytest.mark.asyncio
async def test_worker_timeout_registry_retains_and_cancels_owned_tasks() -> None:
    registry = routes_agent_squads.WorkerTimeoutRegistry()
    never = asyncio.Event()
    task = asyncio.create_task(never.wait())

    registry.track("work-item", task)
    assert registry.active_count == 1
    registry.cancel("work-item")
    await asyncio.sleep(0)

    assert task.cancelled()
    assert registry.active_count == 0


@pytest.mark.asyncio
async def test_worker_timeout_registry_observes_task_failures(caplog: pytest.LogCaptureFixture) -> None:
    registry = routes_agent_squads.WorkerTimeoutRegistry()

    async def _fail() -> None:
        raise RuntimeError("deadline boom")

    with caplog.at_level("ERROR"):
        registry.track("broken-work-item", asyncio.create_task(_fail()))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert registry.active_count == 0
    assert "timeout task failed for broken-work-item" in caplog.text
    assert "deadline boom" in caplog.text


@pytest.mark.asyncio
async def test_worker_presence_registry_retains_and_cancels_owned_tasks() -> None:
    registry = routes_agent_squads.WorkerPresenceRegistry()
    never = asyncio.Event()
    task = asyncio.create_task(never.wait())

    registry.track("work-item", task)
    assert registry.active_count == 1
    registry.cancel("work-item")
    await asyncio.sleep(0)

    assert task.cancelled()
    assert registry.active_count == 0


@pytest.mark.asyncio
async def test_daemon_heartbeats_worker_while_pty_is_alive(tmp_path: Path) -> None:
    app, client = _harness(tmp_path)
    pty = SimpleNamespace(exit_code=None)
    published: list[tuple[str, dict]] = []

    class StubBus:
        async def publish(self, name: str, payload: dict) -> None:
            published.append((name, payload))

    with client as c:
        with app.state.storage.transaction() as conn:
            session = routes_agent_squads.coordination.register_session(
                conn,
                routes_agent_squads.coordination.AgentSessionRegister(
                    runtime_id="copilot",
                    agent_label="Copilot reviewer",
                    project_id="demo-project",
                    coder_thread_id="presence-pty",
                    task="Review the UI",
                ),
            )
            routes_agent_squads.coordination.end_session(conn, session.id)

        task = asyncio.create_task(
            routes_agent_squads._maintain_worker_presence(  # noqa: SLF001
                app.state.storage,
                SimpleNamespace(get=lambda session_id: pty),  # type: ignore[arg-type]
                StubBus(),  # type: ignore[arg-type]
                coordination_session_id=session.id,
                pty_session_id="presence-pty",
                interval_seconds=0.01,
            )
        )
        await asyncio.sleep(0.03)
        pty.exit_code = 0
        await asyncio.wait_for(task, timeout=0.1)

        updated = routes_agent_squads.coordination.get_session(
            app.state.storage.conn, session.id
        )

    assert updated.status.value == "active"
    assert len(published) >= 2
    assert all(name == "v1.coordination.session_heartbeat" for name, _ in published)


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


def test_delegate_without_auto_launch_returns_bare_child(tmp_path: Path) -> None:
    # Backward compatibility: the default (no auto_launch) still returns the bare child, unlaunched.
    _app, client = _harness(tmp_path)
    with client as c:
        squad = _create_squad(c)
        parent = _create_work_item(c, squad["id"], assigned_role_id="planner")
        res = c.post(
            f"/api/v1/agent-work-items/{parent['id']}/delegate",
            json={"title": "Just create it", "assigned_role_id": "reviewer"},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["status"] == "queued"
        assert "launched" not in body


def test_delegate_auto_launch_over_cap_leaves_child_queued(tmp_path: Path) -> None:
    # Plan 3 Phase 3: auto_launch is bounded by the squad's concurrency cap. When the cap is already
    # full the child is created but LEFT QUEUED (with a reason) instead of erroring the delegation.
    # Deterministic + platform-independent: the cap gate fires before any PTY spawn.
    _app, client = _harness(tmp_path)
    with client as c:
        squad = c.post(
            "/api/v1/agent-squads",
            json={
                "project_id": "demo-project",
                "name": "Capped Squad",
                "goal_md": "x",
                "lead_role_id": "planner",
                "max_concurrent": 1,
            },
        ).json()
        # Occupy the single slot with a RUNNING work item (a status change, no real spawn).
        busy = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        assert c.post(
            f"/api/v1/agent-work-items/{busy['id']}/status", json={"status": "running"}
        ).status_code == 200
        parent = _create_work_item(c, squad["id"], assigned_role_id="planner")

        res = c.post(
            f"/api/v1/agent-work-items/{parent['id']}/delegate",
            json={"title": "Overflow work", "assigned_role_id": "reviewer", "auto_launch": True},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["launched"] is None
        assert "queued_reason" in body and "cap" in body["queued_reason"].lower()
        assert body["status"] == "queued"
        # Persisted state (not just the response snapshot) confirms the child never launched.
        items = c.get(f"/api/v1/agent-squads/{squad['id']}").json()["work_items"]
        overflow = next(w for w in items if w["title"] == "Overflow work")
        assert overflow["status"] == "queued"
        assert overflow["pty_session_id"] is None


def test_squad_capacity_reflects_cap_and_running(tmp_path: Path) -> None:
    _app, client = _harness(tmp_path)
    with client as c:
        squad = c.post(
            "/api/v1/agent-squads",
            json={
                "project_id": "demo-project", "name": "Capped", "goal_md": "x",
                "lead_role_id": "planner", "max_concurrent": 2, "token_budget": 1000,
            },
        ).json()
        cap = c.get(f"/api/v1/agent-squads/{squad['id']}/capacity").json()
        assert cap["max_concurrent"] == 2 and cap["running"] == 0
        assert cap["concurrency_available"] == 2 and cap["tokens_remaining"] == 1000
        assert cap["can_launch"] is True

        for _ in range(2):
            wi = _create_work_item(c, squad["id"], assigned_role_id="implementer")
            c.post(f"/api/v1/agent-work-items/{wi['id']}/status", json={"status": "running"})
        cap2 = c.get(f"/api/v1/agent-squads/{squad['id']}/capacity").json()
        assert cap2["running"] == 2 and cap2["concurrency_available"] == 0
        assert cap2["can_launch"] is False


def test_squad_capacity_unlimited_when_uncapped(tmp_path: Path) -> None:
    _app, client = _harness(tmp_path)
    with client as c:
        squad = _create_squad(c)  # no max_concurrent / token_budget -> 0 = unlimited
        cap = c.get(f"/api/v1/agent-squads/{squad['id']}/capacity").json()
        assert cap["max_concurrent"] == 0 and cap["concurrency_available"] is None
        assert cap["token_budget"] == 0 and cap["tokens_remaining"] is None
        assert cap["can_launch"] is True


@posix_only
def test_delegate_auto_launch_spawns_child(tmp_path: Path) -> None:
    app, client = _harness(tmp_path)
    script = tmp_path / "auto-child.sh"
    script.write_text("#!/usr/bin/env bash\nsleep 2\n", encoding="utf-8")
    script.chmod(0o755)
    with client as c:
        squad = _create_squad(c)
        parent = _create_work_item(c, squad["id"], assigned_role_id="planner")
        res = c.post(
            f"/api/v1/agent-work-items/{parent['id']}/delegate",
            json={
                "title": "Launched child",
                "assigned_role_id": "reviewer",
                "preferred_runtime": str(script),
                "auto_launch": True,
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["launched"] is not None
        assert body["status"] == "running"
        assert body["launched"]["work_item_id"] == body["id"]
        c.delete(f"/api/v1/pty/{body['launched']['session_id']}")


@posix_only
def test_delegate_auto_launch_surfaces_real_spawn_failure(tmp_path: Path) -> None:
    # A genuine (non-cap) launch failure must SURFACE as a 4xx -- not be swallowed as a benign
    # "queued" gate. The child is still created (committed before the launch attempt) and left QUEUED
    # for a manual retry once the cause is fixed. Guards the 409-only swallow / re-raise branch.
    _app, client = _harness(tmp_path)
    missing = tmp_path / "does-not-exist-binary"
    with client as c:
        squad = _create_squad(c)
        parent = _create_work_item(c, squad["id"], assigned_role_id="planner")
        res = c.post(
            f"/api/v1/agent-work-items/{parent['id']}/delegate",
            json={
                "title": "Doomed launch",
                "assigned_role_id": "reviewer",
                "preferred_runtime": str(missing),
                "auto_launch": True,
            },
        )
        assert res.status_code == 422, res.text
        items = c.get(f"/api/v1/agent-squads/{squad['id']}").json()["work_items"]
        child = next(w for w in items if w["title"] == "Doomed launch")
        assert child["status"] == "queued"
        assert child["pty_session_id"] is None


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


def test_blocking_handoff_opens_gate_and_stays_in_handoff(tmp_path: Path) -> None:
    _app, client = _harness(tmp_path)
    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="launch-verifier")

        handoff = c.post(
            f"/api/v1/agent-work-items/{item['id']}/handoff",
            json={
                "status": "completed",
                "summary_md": "Launch still misfires because the tile parent catches the click.",
                "files_touched": ["renderer/components/ProjectTile.tsx"],
                "verdict": {
                    "blocking": True,
                    "severity": "critical",
                    "surface_ids": ["apps.projects-grid"],
                    "contract_ids": ["project-launch-action"],
                    "recommended_next_step": "Remove the parent click ambiguity and re-run browser proof.",
                    "summary": "Launch is still broken.",
                    "findings": [
                        {
                            "title": "Launch button reopens the parent card",
                            "severity": "critical",
                            "summary": "The card-level click target still interferes with Launch.",
                            "surface_id": "apps.projects-grid",
                            "contract_id": "project-launch-action",
                        }
                    ],
                },
            },
        )
        assert handoff.status_code == 200, handoff.text
        body = handoff.json()
        assert body["status"] == "handoff"
        assert body["verdict"]["blocking"] is True
        assert body["gate"]["gate_kind"] == "ui-review"


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
        assert session._env["SYNAPSE_RUNTIME_ID"] == str(script)  # noqa: SLF001
        assert session._env["SYNAPSE_PTY_SESSION_ID"] == body["session_id"]  # noqa: SLF001
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

        assert updated["status"] == "handoff"
        assert "without an explicit handoff" in updated["blockers_md"]
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
        assert body["status"] == "paused"

        missing = c.post("/api/v1/agent-squads/does-not-exist/stop")
        assert missing.status_code >= 400


def test_unknown_worker_exit_status_blocks_instead_of_implying_clean_exit(tmp_path: Path) -> None:
    app, client = _harness(tmp_path)
    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        with app.state.storage.transaction() as conn:
            agent_squads.set_work_item_session(
                conn,
                item["id"],
                status=agent_squads.AgentWorkItemStatus.RUNNING,
                pty_session_id="unknown-exit",
                chosen_runtime="codex",
                opened_in_tab=False,
            )
            updated = agent_squads.complete_work_item_from_session_exit(
                conn,
                session_id="unknown-exit",
                exit_code=None,
            )

    assert updated is not None
    assert updated.status == agent_squads.AgentWorkItemStatus.BLOCKED
    assert "exit status was unavailable" in (updated.blockers_md or "")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ConPTY execution proof")
def test_real_pty_finalizer_flows_into_runtime_and_squad_accounting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP launch -> real PTY -> WS subscriber -> canonical REST accounting."""
    app, client = _harness(tmp_path)
    monkeypatch.setattr(
        agent_squads,
        "argv_for_runtime",
        lambda runtime: [
            "powershell.exe", "-NoProfile", "-Command",
            "Write-Output 'tokens used'; Write-Output '49,912'",
        ],
    )
    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        launched = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={"preferred_runtime": "codex", "open_in_tab": False},
        )
        assert launched.status_code == 200, launched.text
        execution_id = launched.json()["execution_id"]
        for _ in range(80):
            receipt = c.get(f"/api/v1/ai/executions/{execution_id}").json()
            if receipt["state"] == "finalized":
                break
            time.sleep(0.1)
        else:
            pytest.fail("real PTY execution did not finalize")
        assert receipt["accounting_state"] == "measured"
        assert receipt["usage"][0]["total_tokens"] == 49_912
        usage = c.get(f"/api/v1/agent-work-items/{item['id']}/tokens").json()
        assert usage[0]["total_tokens"] == 49_912
        rollup = c.get(f"/api/v1/agent-squads/{squad['id']}/token-usage").json()
        assert rollup["total_tokens"] == 49_912


def test_stop_squad_blocks_worker_before_pty_finalization_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client = _harness(tmp_path)
    closed: list[str] = []

    async def _fake_close(session_id: str) -> bool:
        closed.append(session_id)
        # Simulate the finalizer racing with the stop endpoint after a clean
        # process exit. The pre-block must survive this zero exit code.
        with app.state.storage.transaction() as conn:
            agent_squads.complete_work_item_from_session_exit(
                conn,
                session_id=session_id,
                exit_code=0,
            )
        return True

    monkeypatch.setattr(app.state.pty_manager, "get", lambda session_id: SimpleNamespace(exit_code=None))
    monkeypatch.setattr(app.state.pty_manager, "close", _fake_close)

    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(c, squad["id"], assigned_role_id="implementer")
        with app.state.storage.transaction() as conn:
            agent_squads.set_work_item_session(
                conn,
                item["id"],
                status=agent_squads.AgentWorkItemStatus.RUNNING,
                pty_session_id="race-session",
                chosen_runtime="codex",
                opened_in_tab=False,
            )
        stopped = c.post(f"/api/v1/agent-squads/{squad['id']}/stop")
        assert stopped.status_code == 200, stopped.text
        detail = c.get(f"/api/v1/agent-squads/{squad['id']}").json()
        updated = next(entry for entry in detail["work_items"] if entry["id"] == item["id"])

    assert closed == ["race-session"]
    assert updated["status"] == "blocked"
    assert "kill switch" in updated["blockers_md"]


def test_launch_with_missing_cwd_returns_clean_error(tmp_path: Path) -> None:
    # Regression: a work item whose project directory does not exist must yield
    # a clean 422, never crash the daemon (a bad cwd can take winpty/ConPTY --
    # and the whole process -- down at a level Python can't catch).
    app, client = _harness(tmp_path)
    shell = "powershell.exe" if sys.platform == "win32" else "bash"
    with client as c:
        c.post(
            "/api/v1/projects",
            json={
                "id": "ghost",
                "name": "Ghost",
                "path": str(tmp_path / "does-not-exist"),
                "kind": "other",
                "launch_cmd": "echo hi",
            },
        )
        squad = c.post(
            "/api/v1/agent-squads",
            json={"project_id": "ghost", "name": "Ghost Team", "lead_role_id": "boss"},
        ).json()
        wi = c.post(
            f"/api/v1/agent-squads/{squad['id']}/work-items",
            json={"title": "x", "assigned_role_id": "implementer"},
        ).json()
        res = c.post(
            f"/api/v1/agent-work-items/{wi['id']}/launch",
            json={"preferred_runtime": shell, "open_in_tab": False},
        )
        assert res.status_code == 422, res.text
        assert c.get("/api/v1/health").status_code == 200


def test_gemini_automatic_launch_maps_authority_to_approval_mode(tmp_path: Path) -> None:
    """Gemini was added to every role template's preferred runtimes but the argv
    builder still rejected it, so selecting it hard-failed the launch.

    Its --approval-mode is an enforced mode rather than a policy hint, so it maps
    directly onto our authority levels.
    """
    for authority, expected in (
        (agent_squads.AgentExecutionAuthority.OBSERVE, "plan"),
        (agent_squads.AgentExecutionAuthority.WORKSPACE, "auto_edit"),
        (agent_squads.AgentExecutionAuthority.FULL, "yolo"),
    ):
        argv = routes_agent_squads._automatic_worker_argv(  # noqa: SLF001
            ["gemini"],
            runtime="gemini",
            authority=authority,
            prompt_file=(tmp_path / "prompt.md").resolve(),
        )
        mode_index = argv.index("--approval-mode")
        assert argv[mode_index + 1] == expected
        # Headless, or a spawned worker waits forever for a human.
        assert "--prompt" in argv
        assert "explicit handoff" in argv[-1]


def test_chatgpt_parent_forces_online_chat_child_and_never_spawns_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client = _harness(tmp_path)
    with app.state.storage.transaction() as conn:
        parent = coordination.register_session(
            conn,
            coordination.AgentSessionRegister(
                project_id="demo-project",
                runtime_id="chatgpt",
                agent_label="GPT-5.6 Sol parent",
                task="Own the child-agent squad",
            ),
        )

    monkeypatch.setattr(
        routes_agent_squads.activity_module,
        "_owner_session_id_for_squad",
        lambda _conn, _squad_id: parent.id,
    )

    async def fake_run_child(
        worker_id: str,
        prompt: str,
        *,
        timeout: float,
        conversation_url: str | None = None,
        desired_title: str = "",
    ):
        assert worker_id
        assert conversation_url is None
        assert "Review" in desired_title
        assert "ChatGPT UI child-agent rules" in prompt
        assert "Do not delegate work to Claude, Codex, Copilot, Gemini" in prompt
        assert timeout == 180
        return chatgpt_child_agents.ChatGPTChildResult(
            worker_id=worker_id,
            ok=True,
            reply="ChatGPT UI child finished the review.",
            conversation_url="https://chatgpt.com/c/child-proof",
            wall_clock_seconds=190.0,
            ui_duration_seconds=188.0,
        )

    monkeypatch.setattr(app.state.chatgpt_child_pool, "run_child", fake_run_child)

    async def forbidden_pty_spawn(**_kwargs):
        raise AssertionError("ChatGPT child must never spawn a CLI/PTy runtime")

    monkeypatch.setattr(app.state.pty_manager, "spawn", forbidden_pty_spawn)

    with client as c:
        squad = _create_squad(c)
        item = _create_work_item(
            c,
            squad["id"],
            title="Review with a ChatGPT UI child",
            assigned_role_id="reviewer",
        )

        rejected = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={
                "preferred_runtime": "codex",
                "execution_mode": "automatic",
                "timeout_seconds": 180,
                "open_in_tab": False,
            },
        )
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["code"] == "agent_runtime.conflict"
        assert rejected.json()["details"]["required_runtime"] == "chatgpt_web"

        launched = c.post(
            f"/api/v1/agent-work-items/{item['id']}/launch",
            json={
                "execution_mode": "automatic",
                "timeout_seconds": 180,
                "open_in_tab": False,
            },
        )
        assert launched.status_code == 200, launched.text
        payload = launched.json()
        assert payload["runtime"] == "chatgpt_web"
        assert payload["browser_runtime"] is True
        assert payload["worker_chat_id"]
        assert "Review" in payload["worker_chat_title"]
        assert payload["worker_chat_reused"] is False

        deadline = time.time() + 2
        current = None
        while time.time() < deadline:
            current = c.get(
                f"/api/v1/agent-squads/{squad['id']}"
            ).json()["work_items"][0]
            if current["status"] != "running":
                break
            time.sleep(0.02)

        assert current is not None
        assert current["status"] == "handoff"
        assert current["preferred_runtime"] == "chatgpt_web"
        assert current["summary_md"] == "ChatGPT UI child finished the review."
        worker = c.get(f"/api/v1/chatgpt-workers/{payload['worker_chat_id']}")
        assert worker.status_code == 200, worker.text
        worker_body = worker.json()
        assert worker_body["status"] == "idle"
        assert worker_body["conversation_url"] == "https://chatgpt.com/c/child-proof"
        assert item["id"] in worker_body["work_item_ids"]

        timing = c.get("/api/v1/thread-presence/overview")
        assert timing.status_code == 200, timing.text
        timing_body = timing.json()
        assert timing_body["counts"]["threads"] == 1
        assert timing_body["total_work_seconds"] == 188
        request_group = timing_body["groups"][0]
        assert request_group["name"] == squad["name"]
        assert request_group["external_group_key"] == f"squad:{squad['id']}"
        assert request_group["total_work_seconds"] == 188
        tracked_thread = request_group["threads"][0]
        assert tracked_thread["title"] == payload["worker_chat_title"]
        assert tracked_thread["turn_count"] == 1
        assert tracked_thread["total_work_seconds"] == 188
        assert tracked_thread["display_status"] == "idle"

        children = c.get(
            "/api/v1/coordination/sessions",
            params={"project_id": "demo-project", "include_gone": True},
        ).json()
        web_children = [
            session
            for session in children
            if session["parent_session_id"] == parent.id
            and session["runtime_id"] == "chatgpt_web"
        ]
        assert len(web_children) == 1
        assert web_children[0]["seq"] is None
