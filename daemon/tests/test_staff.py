from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> tuple[TestClient, Storage]:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(conn, Project(id="demo-project", name="Demo", path=str(tmp_path), launch_cmd="echo hi"))
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, storage


def test_staff_foundation_seeds_maya_and_avatar_catalog(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    response = client.get("/api/v1/staff")
    assert response.status_code == 200, response.text
    payload = response.json()
    maya = next(member for member in payload["staff"] if member["handle"] == "maya")
    assert maya["display_name"] == "Maya"
    assert maya["title"] == "Growth Director"
    assert maya["role_template_id"] == "growth-director"
    assert maya["personality_id"] == "growth-operator"
    assert maya["avatar_asset_id"] == "solar-flare"
    assert maya["authority_policy"] == "prepare_for_approval"
    assert len(payload["avatar_assets"]) >= 8


def test_staff_profile_expands_role_personality_avatar_and_work(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    response = client.get("/api/v1/staff/maya")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["staff"]["handle"] == "maya"
    assert payload["role"]["id"] == "growth-director"
    assert payload["personality"]["id"] == "growth-operator"
    assert payload["avatar"]["id"] == "solar-flare"
    assert payload["recent_work"] == []


def test_summon_maya_creates_linked_work_item_with_identity(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    response = client.post(
        "/api/v1/staff/maya/summon",
        json={
            "project_id": "demo-project",
            "task": "Find the best growth opportunity",
            "instructions_md": "Compare the current product with its nearest alternatives.",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["work_item"]["assigned_role_id"] == "growth-director"
    assert payload["work_item"]["personality_id"] == "growth-operator"
    linked = storage.conn.execute(
        "SELECT staff_member_id FROM staff_work_items WHERE work_item_id = ?",
        (payload["work_item"]["id"],),
    ).fetchone()
    assert linked is not None
    assert linked["staff_member_id"] == "maya-growth"
    profile = client.get("/api/v1/staff/maya").json()
    assert profile["staff"]["status"] == "working"
    assert profile["recent_work"][0]["title"] == "Find the best growth opportunity"


def test_avatar_can_be_changed_from_catalog(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    response = client.patch("/api/v1/staff/maya", json={"avatar_asset_id": "violet-grid"})
    assert response.status_code == 200, response.text
    assert response.json()["avatar_asset_id"] == "violet-grid"
