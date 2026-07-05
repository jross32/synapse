from __future__ import annotations

import types
from pathlib import Path

from fastapi.testclient import TestClient

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
                id="demo-project",
                name="Demo Project",
                path=str(tmp_path),
                launch_cmd="python -V",
            ),
        )
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return app, client, storage


def test_coder_thread_crud_and_context(tmp_path: Path) -> None:
    _app, client, _storage = _harness(tmp_path)
    with client as c:
        created = c.post(
            "/api/v1/projects/demo-project/coder-threads",
            json={
                "title": "New thread",
                "active_runtime_id": "codex",
                "active_provider": "openai",
                "active_model": "codex",
            },
        )
        assert created.status_code == 201, created.text
        thread_id = created.json()["id"]

        listed = c.get("/api/v1/projects/demo-project/coder-threads")
        assert listed.status_code == 200, listed.text
        assert listed.json()["threads"][0]["thread"]["id"] == thread_id

        msg = c.post(
            f"/api/v1/coder-threads/{thread_id}/messages",
            json={"role": "user", "content_md": "Build a tiny benchmark app."},
        )
        assert msg.status_code == 201, msg.text

        runtime = c.post(
            f"/api/v1/coder-threads/{thread_id}/runtime",
            json={"runtime_id": "claude", "provider": "anthropic", "model": "claude-code", "reason": "compare"},
        )
        assert runtime.status_code == 200, runtime.text
        assert runtime.json()["thread"]["active_runtime_id"] == "claude"

        review = c.post(
            f"/api/v1/coder-threads/{thread_id}/review-passes",
            json={"requested_runtime_id": "copilot", "requested_provider": "github", "title": "Copilot review"},
        )
        assert review.status_code == 201, review.text

        detail = c.get(f"/api/v1/coder-threads/{thread_id}")
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["messages"][0]["content_md"] == "Build a tiny benchmark app."
        assert body["runtime_switches"][0]["to_runtime_id"] == "claude"
        assert body["review_passes"][0]["requested_runtime_id"] == "copilot"

        context = c.get(f"/api/v1/coder-threads/{thread_id}/context")
        assert context.status_code == 200, context.text
        payload = context.json()
        assert payload["thread"]["id"] == thread_id
        assert payload["files_count"] == 0
        assert payload["records_summary"] == {"adrs": 0, "backlog": 0, "versions": 0}
        assert payload["preferences"]["advanced_terminal_enabled"] is False


def test_ai_context_includes_coder_threads(tmp_path: Path) -> None:
    _app, client, _storage = _harness(tmp_path)
    with client as c:
        created = c.post(
            "/api/v1/projects/demo-project/coder-threads",
            json={"title": "Context thread", "active_runtime_id": "codex"},
        )
        assert created.status_code == 201
        payload = c.get("/api/v1/ai/context").json()
        assert any(thread["id"] == created.json()["id"] for thread in payload["coder_threads"])


def test_dispatch_review_and_preferences_routes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _app, client, _storage = _harness(tmp_path)
    writes: list[tuple[str, bytes]] = []

    class FakeSession:
        def __init__(self, session_id: str, project_id: str | None) -> None:
            self.session_id = session_id
            self.project_id = project_id

        async def write(self, payload: bytes) -> None:
            writes.append((self.session_id, payload))

        def summary(self):  # type: ignore[no-untyped-def]
            return types.SimpleNamespace(
                session_id=self.session_id,
                argv=["codex"],
                cwd=str(tmp_path),
                started_at="2026-06-28T00:00:00+00:00",
                exit_code=None,
                rows=24,
                cols=80,
                project_id=self.project_id,
            )

    async def fake_spawn(  # type: ignore[no-untyped-def]
        self,
        argv,
        cwd=None,
        env=None,
        rows=24,
        cols=80,
        project_id=None,
        session_id=None,
    ):
        return FakeSession(session_id or f"fake-{len(writes) + 1}", project_id)

    monkeypatch.setattr("synapse_daemon.pty_sessions.PtySessionManager.spawn", fake_spawn)

    with client as c:
        created = c.post(
            "/api/v1/projects/demo-project/coder-threads",
            json={"title": "Dispatch me", "active_runtime_id": "codex"},
        )
        assert created.status_code == 201, created.text
        thread_id = created.json()["id"]

        prefs = c.patch(
            "/api/v1/coder-workspace/preferences",
            json={"advanced_terminal_enabled": True},
        )
        assert prefs.status_code == 200, prefs.text
        assert prefs.json()["advanced_terminal_enabled"] is True

        dispatched = c.post(
            f"/api/v1/coder-threads/{thread_id}/dispatch",
            json={"content_md": "Build a better Synapse chat shell."},
        )
        assert dispatched.status_code == 201, dispatched.text
        dispatch_body = dispatched.json()
        assert dispatch_body["message"]["content_md"] == "Build a better Synapse chat shell."
        assert dispatch_body["run"]["surface_kind"] == "coder-thread-dispatch"
        assert dispatch_body["session"]["session_id"] == "fake-1"
        assert writes and writes[0][1].endswith(b"\r")

        review = c.post(
            f"/api/v1/coder-threads/{thread_id}/review-passes",
            json={"requested_runtime_id": "claude", "title": "Claude review"},
        )
        assert review.status_code == 201, review.text
        review_id = review.json()["id"]

        launched_review = c.post(
            f"/api/v1/coder-threads/{thread_id}/review-passes/{review_id}/launch",
            json={},
        )
        assert launched_review.status_code == 200, launched_review.text
        review_body = launched_review.json()
        assert review_body["run"]["surface_kind"] == "coder-review-pass"
        assert review_body["session"]["session_id"] == "fake-2"

        verdict = c.post(
            f"/api/v1/coder-review-passes/{review_id}/verdict",
            json={
                "summary_md": "Launch path is still broken.",
                "verdict": {
                    "blocking": True,
                    "severity": "critical",
                    "surface_ids": ["apps.projects-grid"],
                    "contract_ids": ["project-launch-action"],
                    "recommended_next_step": "Fix the launch path and attach browser proof.",
                    "summary": "Launch still regresses.",
                    "findings": [
                        {
                            "title": "Launch button no-op",
                            "severity": "critical",
                            "summary": "The launch action did not complete successfully.",
                            "surface_id": "apps.projects-grid",
                            "contract_id": "project-launch-action",
                        }
                    ],
                },
            },
        )
        assert verdict.status_code == 200, verdict.text
        assert verdict.json()["gate"]["gate_kind"] == "ui-review"

        detail = c.get(f"/api/v1/coder-threads/{thread_id}")
        assert detail.status_code == 200, detail.text
        linked_runs = detail.json()["linked_runs"]
        assert len(linked_runs) == 2
        assert detail.json()["review_passes"][0]["verdict"]["blocking"] is True
