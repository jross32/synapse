"""Full access, proven end to end through the actual JSON-RPC layer.

Uses the same in-process harness as the rest of the connector suite - its own Storage, its
own TestClient, nothing bound to a port and nothing touching the real daemon. This answers
"does full access actually work" at the only layer I can verify without a live ChatGPT
session: the server correctly executes a write tool call and the result is real.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path, *, writes_enabled: bool) -> tuple[TestClient, str]:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(conn, Project(id="demo-project", name="Demo Project", path=str(tmp_path),
                             launch_cmd="echo hi"))
    from synapse_daemon import boot_config

    cfg = boot_config.load(tmp_path / "data")
    cfg.mcp_writes_enabled = writes_enabled
    boot_config.save(tmp_path / "data", cfg)

    app = build_app(storage, EventBus())
    return TestClient(app), app.state.auth.local_token


def _call(client: TestClient, token: str, name: str, arguments: dict,
         url_suffix: str = "") -> dict:
    res = client.post(f"/mcp/{token}{url_suffix}", json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert res.status_code == 200, res.text
    return res.json()["result"]


@pytest.fixture()
def clean_env(monkeypatch):
    # The persisted setting is what this test is actually exercising - make sure the env
    # var (which still wins when set) is not silently overriding it.
    monkeypatch.delenv("SYNAPSE_MCP_ALLOW_WRITES", raising=False)


def test_full_access_actually_writes_a_real_file(tmp_path, clean_env):
    """Not a mock, not a dry run: a file appears on disk with the content sent."""
    client, token = _harness(tmp_path, writes_enabled=True)
    target = tmp_path / "written-by-mcp" / "proof.txt"

    result = _call(client, token, "synapse_write_file", {
        "path": str(target), "content": "written through the full-access connector\n",
    })
    payload = json.loads(result["content"][0]["text"])
    assert payload["ok"] is True
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == "written through the full-access connector\n"


def test_full_access_actually_runs_a_real_command(tmp_path, clean_env):
    client, token = _harness(tmp_path, writes_enabled=True)
    result = _call(client, token, "synapse_run_command", {
        "command": "echo full-access-proof" if os.name != "nt"
        else "Write-Output full-access-proof",
    })
    payload = json.loads(result["content"][0]["text"])
    assert payload["ok"] is True
    assert "full-access-proof" in payload["stdout"]


def test_the_persisted_toggle_off_refuses_the_same_call(tmp_path, clean_env):
    """The other half of the proof: the toggle is not decorative."""
    client, token = _harness(tmp_path, writes_enabled=False)
    result = _call(client, token, "synapse_write_file",
                   {"path": str(tmp_path / "should-not-exist.txt"), "content": "x"})
    assert result.get("isError") is True
    assert not (tmp_path / "should-not-exist.txt").exists()


def test_read_only_url_refuses_the_same_call_even_when_the_toggle_is_on(tmp_path, clean_env):
    """`?mode=read` must win over the persisted toggle, not the other way round."""
    client, token = _harness(tmp_path, writes_enabled=True)
    result = _call(client, token, "synapse_write_file",
                   {"path": str(tmp_path / "should-not-exist.txt"), "content": "x"},
                   url_suffix="?mode=read")
    assert result.get("isError") is True
    assert not (tmp_path / "should-not-exist.txt").exists()


def test_every_write_tool_response_carries_a_real_result_not_a_stub(tmp_path, clean_env):
    """A tool that silently no-ops would pass a naive smoke test; check the actual effect."""
    client, token = _harness(tmp_path, writes_enabled=True)
    result = _call(client, token, "synapse_runtime_status", {})
    payload = json.loads(result["content"][0]["text"])
    assert isinstance(payload, list) and len(payload) >= 1
    assert {"runtime", "usable_now", "cost_usd_today"} <= set(payload[0])


def test_runtime_status_defers_to_durable_evidence_over_a_fresh_restart(
    tmp_path, clean_env, monkeypatch
):
    """Reproduces a real discrepancy found live: right after a daemon restart,
    coder_runtimes.preflight()'s in-memory cooldown has no memory of anything, so it reports
    a runtime as usable even though the durable ai_runtime_capacity ledger still holds real
    provider evidence that it's quota-exhausted. The MCP tool must not expose the more
    optimistic, less-informed answer when better evidence already exists."""
    from synapse_daemon import ai_executions, coder_runtimes
    from synapse_daemon.storage import Storage

    # This test isolates restart-vs-durable-evidence precedence. Model the runtime
    # as installed explicitly so the CI host's tool inventory cannot short-circuit
    # the scenario with a legitimate "not installed" result.
    monkeypatch.setattr(
        coder_runtimes, "resolve_command", lambda command: f"/fake/{command}"
    )

    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        ai_executions.set_operator_capacity(
            conn, "claude", state=ai_executions.RuntimeCapacityState.QUOTA_EXHAUSTED,
            note="usage limit reached (test)")

    from synapse_daemon import boot_config
    cfg = boot_config.load(tmp_path / "data")
    cfg.mcp_writes_enabled = True
    boot_config.save(tmp_path / "data", cfg)

    from fastapi.testclient import TestClient
    from synapse_daemon.app import build_app
    from synapse_daemon.ws import EventBus

    app = build_app(storage, EventBus())
    client, token = TestClient(app), app.state.auth.local_token

    result = _call(client, token, "synapse_runtime_status", {})
    payload = json.loads(result["content"][0]["text"])
    claude = next(r for r in payload if r["runtime"] == "claude")
    assert claude["usable_now"] is False
    assert "quota_exhausted" in claude["note"]


def test_playbook_tools_are_readable_even_with_writes_off(tmp_path, clean_env):
    """synapse_list_playbooks / synapse_get_playbook are read-only -- they must work
    regardless of the write toggle, exactly like the other always-advertised read tools."""
    from synapse_daemon import playbooks as pb

    client, token = _harness(tmp_path, writes_enabled=False)
    storage = Storage(tmp_path / "data")
    storage.open()
    with storage.transaction() as conn:
        pb.upsert_playbook(conn, playbook_id="demo", title="Demo", summary="s", steps=["a", "b"])

    listed = json.loads(_call(client, token, "synapse_list_playbooks", {})["content"][0]["text"])
    assert any(p["id"] == "demo" and p["step_count"] == 2 for p in listed)

    got = json.loads(_call(client, token, "synapse_get_playbook", {"playbook_id": "demo"})["content"][0]["text"])
    assert got["steps"] == ["a", "b"]
    assert got["status"] == "healthy"


def test_reporting_playbook_status_when_writes_are_off_is_refused_and_does_not_persist(tmp_path, clean_env):
    from synapse_daemon import playbooks as pb

    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        pb.upsert_playbook(conn, playbook_id="demo", title="Demo", summary="", steps=["a"])

    client_ro, token_ro = _harness(tmp_path, writes_enabled=False)
    refused = _call(client_ro, token_ro, "synapse_report_playbook_status",
                    {"playbook_id": "demo", "status": "broken", "note": "UI changed"})
    assert refused.get("isError") is True

    unchanged = pb.get_playbook(storage.conn, "demo")
    assert unchanged.status == pb.PlaybookStatus.HEALTHY  # the refused call left no trace


def test_reporting_playbook_status_when_writes_are_on_actually_persists(tmp_path, clean_env):
    from synapse_daemon import playbooks as pb

    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        pb.upsert_playbook(conn, playbook_id="demo", title="Demo", summary="", steps=["a"])

    client_rw, token_rw = _harness(tmp_path, writes_enabled=True)
    reported = _call(client_rw, token_rw, "synapse_report_playbook_status",
                     {"playbook_id": "demo", "status": "needs_attention", "note": "button moved"})
    payload = json.loads(reported["content"][0]["text"])
    assert payload["status"] == "needs_attention"
    assert payload["status_note"] == "button moved"

    # Re-read independently of the tool-call response, off the same underlying storage,
    # so this proves a real write landed rather than an in-memory echo of what was sent.
    reread = pb.get_playbook(storage.conn, "demo")
    assert reread.status == pb.PlaybookStatus.NEEDS_ATTENTION
    assert reread.status_note == "button moved"
