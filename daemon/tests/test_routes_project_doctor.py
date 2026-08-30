from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def test_project_doctor_route_reports_registered_project(tmp_path: Path) -> None:
    project_root = tmp_path / "demo"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text('[project]\nname="demo"\n', encoding="utf-8")

    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(conn, Project(id="demo", name="Demo", path=str(project_root), launch_cmd="python app.py"))

    app = build_app(storage, EventBus())
    app.state.bound_host = "127.0.0.1"
    app.state.bound_port = 7878
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    with client as c:
        response = c.get("/api/v1/project-doctor/demo")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["id"] == "demo"
    assert payload["doctor"]["stack"]["python"] is True
    assert payload["doctor"]["healthy"] is True

    unauthenticated = TestClient(app)
    response = unauthenticated.get("/api/v1/project-doctor/demo")
    assert response.status_code == 401
