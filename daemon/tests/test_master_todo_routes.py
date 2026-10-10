from fastapi import FastAPI
from fastapi.testclient import TestClient
from synapse_daemon.routes_master_todo import build_master_todo_router


def test_planner_routes(tmp_path):
    app = FastAPI()
    app.include_router(build_master_todo_router(tmp_path), prefix="/api/v1")
    client = TestClient(app)
    response = client.get("/api/v1/master-todo")
    assert response.status_code == 200
    assert len(response.json()["tasks"]) == 3
    revision = response.json()["revision"]
    data = {"action": "complete", "task_id": "daily-review", "day": "2026-10-08", "expected_revision": revision, "event_id": "evt1"}
    assert client.post("/api/v1/master-todo", json=data).json()["tasks"][2]["done_today"]
    assert client.post("/api/v1/master-todo", json=data).json()["revision"] == revision + 1
    data["event_id"] = "evt2"
    assert client.post("/api/v1/master-todo", json=data).status_code == 409
    assert not client.get("/api/v1/master-todo?day=2026-10-09").json()["tasks"][2]["done_today"]
