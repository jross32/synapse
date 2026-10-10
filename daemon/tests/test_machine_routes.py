from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def test_machine_api_register_list_and_rename(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())

    # Reuse one AnyIO portal per test. Creating a new portal for every request
    # has caused native thread-start crashes on heavily loaded Windows hosts.
    with TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token}) as client:
        heartbeat = client.post("/api/v1/machines/local/heartbeat")
        assert heartbeat.status_code == 200
        machine = heartbeat.json()["machine"]
        assert machine["platform"] in {"windows", "linux", "darwin"}

        listed = client.get("/api/v1/machines")
        assert [item["id"] for item in listed.json()["machines"]] == [machine["id"]]

        renamed = client.patch(f"/api/v1/machines/{machine['id']}", json={"name": "Power Machine"})
        assert renamed.status_code == 200
        assert renamed.json()["machine"]["name"] == "Power Machine"

        again = client.post("/api/v1/machines/local/heartbeat")
        assert again.status_code == 200
        assert again.json()["machine"]["name"] == "Power Machine"


def test_machine_api_requires_auth(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    with TestClient(app) as client:
        assert client.get("/api/v1/machines").status_code == 401
