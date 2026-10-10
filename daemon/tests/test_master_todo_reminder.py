from fastapi import FastAPI
from fastapi.testclient import TestClient
from synapse_daemon.routes_master_todo import build_master_todo_router


def test_reminder_configuration(tmp_path):
    app = FastAPI()
    app.include_router(build_master_todo_router(tmp_path), prefix="/api/v1")
    client = TestClient(app)
    base = "/api/v1/master-todo"
    first = client.get(base).json()
    assert first["reminder_time"] is None
    update = client.put(base + "/reminder", json={"reminder_time": "08:30", "expected_revision": first["revision"]})
    assert update.status_code == 200
    assert update.json()["reminder_time"] == "08:30"
    assert client.get(base).json()["reminder_time"] == "08:30"
    assert client.put(base + "/reminder", json={"reminder_time": "09:00", "expected_revision": first["revision"]}).status_code == 409
    assert client.put(base + "/reminder", json={"reminder_time": "25:00"}).status_code == 422
    assert client.put(base + "/reminder", json={"reminder_time": None}).json()["reminder_time"] is None
