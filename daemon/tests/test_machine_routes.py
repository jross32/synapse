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

        inventory = client.get("/api/v1/machines/local/inventory")
        assert inventory.status_code == 200
        assert "tools" in inventory.json()["inventory"]
        assert inventory.json()["inventory"]["hostname"]

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

def test_copy_registered_project_requires_confirmation(tmp_path: Path, monkeypatch):
    from synapse_daemon import projects
    from synapse_daemon.projects import Project
    original = tmp_path / "test-source"
    original.mkdir()
    (original / "app.py").write_text("print(42)", encoding="utf-8")
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        projects.create(conn, Project(id="test-app", name="Test App", path=str(original), launch_cmd="python app.py"))
    app = build_app(storage, EventBus())
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token}) as client:
        preview = client.get("/api/v1/machines/local/projects/test-app/copy-preview")
        assert preview.status_code == 200, preview.text
        assert preview.json()["preview"]["files"] == 1
        refused = client.post("/api/v1/machines/local/projects/test-app/copy",
                              json={"folder_name":"replica","confirmed":False})
        assert refused.status_code == 409
        copied = client.post("/api/v1/machines/local/projects/test-app/copy",
                             json={"folder_name":"replica","confirmed":True})
        assert copied.status_code == 200, copied.text
        assert copied.json()["copy"]["verified"] is True
        assert (tmp_path / "Synapse Imports" / "replica" / "app.py").read_text() == "print(42)"
        repeated = client.post("/api/v1/machines/local/projects/test-app/copy",
                               json={"folder_name":"replica","confirmed":True})
        assert repeated.status_code == 409
