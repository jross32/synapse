from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.process_manager import ProcessManager
from synapse_daemon.projects import Project, ProjectKind, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    repo_path = tmp_path / "repo"
    repo_path.mkdir(parents=True, exist_ok=True)
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="demo-project",
                name="Demo Project",
                path=str(repo_path),
                launch_cmd="echo hi",
                kind=ProjectKind.LIBRARY,
            ),
        )
    bus = EventBus()
    pm = ProcessManager(storage, bus)
    app = build_app(storage, bus, process_manager=pm)
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client


def test_catalog_seeds_components_and_recipes(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/ai-factory/catalog")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["counts"]["components"] >= 20
        assert body["counts"]["recipes"] >= 30
        assert body["mission_profiles"]


def test_source_can_promote_to_component(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        created = c.post(
            "/api/v1/ai-sources",
            json={
                "id": "sample-site",
                "label": "Sample site",
                "source_type": "web",
                "url": "https://example.com",
                "reuse_posture": "reference_only",
                "provenance_summary": "Reference-only source for recipe inspiration.",
            },
        )
        assert created.status_code == 201, created.text
        promoted = c.post(
            "/api/v1/ai-sources/sample-site/promote",
            json={
                "target_type": "component",
                "new_id": "sample-nav-pack",
                "name": "Sample Nav Pack",
                "family": "nav_pack",
                "description": "Promoted from a sample source.",
            },
        )
        assert promoted.status_code == 201, promoted.text
        assert promoted.json()["id"] == "sample-nav-pack"


def test_spawn_case_creates_lineage_graph(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        created = c.post(
            "/api/v1/ai-cases",
            json={
                "case_mode": "benchmark",
                "mission_profile_id": "multi-candidate-bakeoff",
                "intent": {"goal_md": "Compare a few candidate app directions."},
                "targets": {"primary_project_id": "demo-project"},
            },
        )
        assert created.status_code == 201, created.text
        parent_id = created.json()["case"]["id"]
        child = c.post(
            f"/api/v1/ai-cases/{parent_id}/spawn",
            json={
                "candidate_label": "Candidate A",
                "spawn_reason": "Variant A for the bakeoff",
                "intent": {"goal_md": "Variant A"},
            },
        )
        assert child.status_code == 201, child.text
        graph = c.get(f"/api/v1/ai-cases/{parent_id}/graph")
        assert graph.status_code == 200, graph.text
        payload = graph.json()
        assert len(payload["nodes"]) == 2
        assert payload["edges"][0]["parent_case_id"] == parent_id
