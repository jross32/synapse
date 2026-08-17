"""Tests for the AI-facing context endpoint (v0.1.29 · ADR-0002 Phase B)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon import coder_workspace
from synapse_daemon import ai_executions
from synapse_daemon import coordination
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="demo",
                name="Demo",
                path=str(tmp_path),
                launch_cmd="echo hi",
            ),
        )
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client


def test_ai_context_returns_versioned_digest(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/ai/context")
        assert res.status_code == 200
        body = res.json()
        assert body["schema"] == "synapse.ai.context/v1"
        # The demo project is in there.
        ids = [p["id"] for p in body["projects"]]
        assert "demo" in ids
        demo = next(p for p in body["projects"] if p["id"] == "demo")
        assert demo["ai_context"]["path"].endswith(".synapse-ai-context.md")
        assert "agent_squads" in body
        assert "agent_role_templates" in body
        # Endpoints list is non-empty -- this is the "how do I do X" pointer
        # for AI sessions.
        assert any(e["path"] == "/api/v1/projects" for e in body["endpoints_for_ai"])
        assert any(e["path"] == "/api/v1/ai/health-report" for e in body["endpoints_for_ai"])
        assert body["runtime_execution"]["schema"] == "synapse.ai.runtimes/v1"
        assert body["runtime_execution"]["endpoints"]["readiness_and_usage"] == (
            "GET /api/v1/ai/runtimes"
        )


def test_ai_runtime_endpoint_exposes_null_unknown_and_durable_capacity(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    storage = client.app.state.storage
    with storage.transaction() as conn:
        ai_executions.reserve_execution(
            conn,
            kind="agent_work_item",
            project_id="demo",
            runtime_id="codex",
            source_type="agent_work_item",
            source_id="runtime-api-test",
            pty_session_id="runtime-api-pty",
        )
        ai_executions.finalize_pty_execution(
            conn,
            pty_session_id="runtime-api-pty",
            output=b"answer without a usage footer",
            exit_code=0,
            work_outcome="handoff",
        )
    with client as c:
        response = c.get("/api/v1/ai/runtimes?project_id=demo&runtime_id=codex")
        assert response.status_code == 200
        body = response.json()
        assert body["schema"] == "synapse.ai.runtimes/v1"
        assert body["capacity"][0]["runtime_id"] == "codex"
        assert body["capacity"][0]["state"] == "available"
        assert body["executions"][0]["accounting_state"] == "unreported"
        assert body["executions"][0]["usage"] == []
        assert "null means unavailable" in body["measurement_note"]

        detail = c.get(f"/api/v1/ai/executions/{body['executions'][0]['id']}")
        assert detail.status_code == 200
        assert detail.json()["runtime_id"] == "codex"

        openapi = c.get("/api/v1/openapi.json").json()
        runtime_schema = openapi["paths"]["/api/v1/ai/runtimes"]["get"]["responses"]["200"]
        assert runtime_schema["content"]["application/json"]["schema"]["$ref"].endswith(
            "/AIRuntimesResponse"
        )


def test_worker_runtime_reads_are_project_and_work_item_scoped(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    storage = client.app.state.storage
    with storage.transaction() as conn:
        own = ai_executions.reserve_execution(
            conn, kind="agent_work_item", project_id="demo", runtime_id="codex",
            source_type="agent_work_item", source_id="own-work", pty_session_id="own-pty",
        )
        foreign = ai_executions.reserve_execution(
            conn, kind="agent_work_item", project_id=None, runtime_id="claude",
            source_type="agent_work_item", source_id="foreign-work", pty_session_id="foreign-pty",
        )
        session = coordination.register_session(
            conn,
            coordination.AgentSessionRegister(
                project_id="demo", runtime_id="codex", agent_label="Scoped worker",
                task="Read own receipt",
            ),
        )
        credential = coordination.issue_session_credential(
            conn, session.id, authority="observe", ttl_seconds=600,
            work_item_id="own-work", squad_id=None,
        )
    headers = {"X-Synapse-Token": credential, "X-Synapse-Session": session.id}
    worker = TestClient(client.app, headers=headers)
    with worker as c:
        listing = c.get("/api/v1/ai/runtimes")
        assert listing.status_code == 200
        assert {row["id"] for row in listing.json()["executions"]} == {own.id}
        assert c.get(f"/api/v1/ai/executions/{own.id}").status_code == 200
        denied = c.get(f"/api/v1/ai/executions/{foreign.id}")
        assert denied.status_code == 403
        assert denied.json()["code"] == "auth.worker_scope_denied"


def test_local_operator_can_acknowledge_reset_without_claiming_ready(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    storage = client.app.state.storage
    with storage.transaction() as conn:
        ai_executions.reserve_execution(
            conn, kind="agent_work_item", project_id="demo", runtime_id="copilot",
            source_type="agent_work_item", source_id="quota-work", pty_session_id="quota-pty",
        )
        ai_executions.finalize_pty_execution(
            conn, pty_session_id="quota-pty",
            output=b"You have exceeded your monthly quota", exit_code=1,
            work_outcome="blocked",
        )
    with client as c:
        blocked = next(
            row for row in c.get("/api/v1/ai/runtimes").json()["capacity"]
            if row["runtime_id"] == "copilot"
        )
        assert blocked["state"] == "quota_exhausted"
        reset = c.post(
            "/api/v1/ai/runtimes/copilot/recheck",
            json={
                "acknowledge_provider_reset": True,
                "note": "Provider dashboard shows the monthly allowance reset.",
            },
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["state"] == "unknown"
        assert reset.json()["usable_now"] is False
        assert reset.json()["eligible_for_attempt"] is True


def test_local_operator_can_attest_known_quota_without_provider_call(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        response = c.post(
            "/api/v1/ai/runtimes/copilot/capacity",
            json={
                "state": "quota_exhausted",
                "note": "Copilot CLI reported the monthly quota was exceeded before this run.",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["state"] == "quota_exhausted"
        assert response.json()["evidence_source"] == "user_reported"
        assert response.json()["eligible_for_attempt"] is False
        audit_row = c.get("/api/v1/audit").json()["entries"]
        assert any(
            row["entity_type"] == "ai_runtime"
            and row["entity_id"] == "copilot"
            and row["action"] == "capacity.attest"
            for row in audit_row
        )


def test_ai_context_requires_auth(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    unauthed = TestClient(app)
    assert unauthed.get("/api/v1/ai/context").status_code == 401


def test_ai_context_inlines_files_per_project(tmp_path: Path) -> None:
    """ADR-0003 Phase A + D -- the context payload exposes uploaded files
    by project so a Claude session can orient on prompt 1."""

    import io as _io

    client = _harness(tmp_path)
    with client as c:
        res = c.post(
            "/api/v1/projects/demo/files",
            files=[("files", ("ai-context.md", _io.BytesIO(b"hello AI"), "text/markdown"))],
        )
        assert res.status_code == 200

        body = c.get("/api/v1/ai/context").json()
        demo = next(p for p in body["projects"] if p["id"] == "demo")
        assert demo["files_count"] == 1
        assert demo["files"][0]["original_name"] == "ai-context.md"

        # Shared scope shows up too.
        c.post(
            "/api/v1/files",
            files=[("files", ("shared.md", _io.BytesIO(b"global"), "text/markdown"))],
        )
        body = c.get("/api/v1/ai/context").json()
        assert any(f["original_name"] == "shared.md" for f in body["shared_files"])


def test_ai_health_report_includes_latest_successful_review_pass(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="demo",
                name="Demo",
                path=str(tmp_path),
                launch_cmd="echo hi",
            ),
        )
        thread = coder_workspace.create_thread(
            conn,
            "demo",
            coder_workspace.CoderThreadCreate(title="Main build thread"),
        )
        review_pass = coder_workspace.create_review_pass(
            conn,
            thread.id,
            coder_workspace.CoderReviewPassCreate(
                title="UX reviewer pass",
                summary_md="Checked the main shell for clarity and state handling.",
            ),
        )
        conn.execute(
            "UPDATE coder_review_passes SET status = ?, updated_at = ? WHERE id = ?",
            (
                coder_workspace.CoderReviewPassStatus.COMPLETED.value,
                "2026-07-29T05:00:00Z",
                review_pass.id,
            ),
        )
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    with client as c:
        res = c.get("/api/v1/ai/health-report")
        assert res.status_code == 200
        body = res.json()
        latest = body["review"]["latest_successful_pass"]
        assert latest["id"] == review_pass.id
        assert latest["thread_id"] == thread.id
        assert latest["thread_title"] == "Main build thread"
        assert latest["title"] == "UX reviewer pass"
        assert latest["summary_md"] == "Checked the main shell for clarity and state handling."
