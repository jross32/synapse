from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from synapse_daemon import coder_runtimes
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


@pytest.fixture(autouse=True)
def _pretend_review_runtimes_are_installed(monkeypatch) -> None:
    monkeypatch.setattr(coder_runtimes, "available", lambda runtime: True)


def _client(tmp_path: Path) -> TestClient:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="smart-review-demo",
                name="Smart Review Demo",
                path=str(tmp_path),
                launch_cmd="echo hi",
            ),
        )
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def _payload() -> dict:
    return {
        "changed_files": ["src/app.py", "tests/test_app.py"],
        "diff_text": "+def answer():\n+    return 42\n",
        "primary_runtime": "codex",
    }


def test_smart_review_is_openapi_and_ai_discoverable(tmp_path: Path) -> None:
    client = _client(tmp_path)
    openapi = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/review/engine/plan/{project_id}" in openapi["paths"]
    assert "/api/v1/review/engine/queue/{project_id}" in openapi["paths"]

    context = client.get("/api/v1/ai/context")
    assert context.status_code == 200, context.text
    advertised = " ".join(item["path"] for item in context.json()["endpoints_for_ai"])
    assert "/api/v1/review/engine/plan/{project_id}" in advertised
    assert "/api/v1/review/engine/queue/{project_id}" in advertised


def test_smart_review_plan_and_queue_reuse_coder_review_passes(tmp_path: Path) -> None:
    client = _client(tmp_path)
    plan_response = client.post("/api/v1/review/engine/plan/smart-review-demo", json=_payload())
    assert plan_response.status_code == 200, plan_response.text
    plan = plan_response.json()
    assert plan["ai_review_required"] is True
    assert plan["review_passes"][0]["requested_runtime_id"] == "claude"

    queued_response = client.post("/api/v1/review/engine/queue/smart-review-demo", json=_payload())
    assert queued_response.status_code == 201, queued_response.text
    queued = queued_response.json()
    assert queued["queued"]
    launch_url = queued["queued"][0]["launch_url"]
    assert launch_url.startswith("/api/v1/coder-threads/")
    assert launch_url.endswith("/launch")


def test_queue_uses_dedicated_engine_thread_when_project_already_has_threads(tmp_path: Path) -> None:
    client = _client(tmp_path)
    existing = client.post(
        "/api/v1/projects/smart-review-demo/coder-threads",
        json={"title": "Existing normal chat", "active_runtime_id": "codex"},
    )
    assert existing.status_code == 201, existing.text
    normal_thread_id = existing.json()["thread"]["id"] if "thread" in existing.json() else existing.json()["id"]

    queued_response = client.post("/api/v1/review/engine/queue/smart-review-demo", json=_payload())
    assert queued_response.status_code == 201, queued_response.text
    queued = queued_response.json()
    assert queued["thread"]["id"] != normal_thread_id
    assert queued["thread"]["metadata"]["created_by"] == "review-engine"
    assert queued["queued"][0]["review_pass"]["metadata"]["budget_kind"] == "aggregate_planning_reserve"
