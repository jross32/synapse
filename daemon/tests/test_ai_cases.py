from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from synapse_daemon import ai_cases
from synapse_daemon.app import build_app
from synapse_daemon.process_manager import ProcessManager
from synapse_daemon.projects import Project, ProjectKind, create
from synapse_daemon import routes_ai_cases
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX PTY only in tests")
git_required = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("# demo\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Synapse Tests"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    repo_path = tmp_path / "repo"
    neighbor_path = tmp_path / "neighbor"
    _init_git_repo(repo_path)
    _init_git_repo(neighbor_path)
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
        create(
            conn,
            Project(
                id="neighbor-project",
                name="Neighbor Project",
                path=str(neighbor_path),
                launch_cmd="echo hi",
                kind=ProjectKind.LIBRARY,
            ),
        )
    bus = EventBus()
    pm = ProcessManager(storage, bus)
    app = build_app(storage, bus, process_manager=pm)
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return app, client, storage, pm


def _patch_fake_spawn(monkeypatch: pytest.MonkeyPatch, app) -> None:
    sessions: dict[str, object] = {}

    async def fake_spawn(*, argv, cwd, env=None, rows=24, cols=80, project_id=None):  # type: ignore[override]
        session_id = f"sid-{len(sessions) + 1}"

        class _Session:
            exit_code = None
            pid = 42

            def __init__(self) -> None:
                self.session_id = session_id
                self.argv = argv
                self.cwd = cwd

            def summary(self):
                return SimpleNamespace(
                    session_id=session_id,
                    pid=42,
                    cwd=cwd,
                    argv=argv,
                    started_at="2026-06-27T00:00:00+00:00",
                    exit_code=None,
                )

        session = _Session()
        sessions[session_id] = session
        return session

    monkeypatch.setattr(app.state.pty_manager, "spawn", fake_spawn)
    monkeypatch.setattr(app.state.pty_manager, "get", lambda session_id: sessions.get(session_id))


def test_create_case_persists_bundle_and_targets(tmp_path: Path) -> None:
    _app, client, storage, _pm = _harness(tmp_path)
    with client as c:
        res = c.post(
            "/api/v1/ai-cases",
            json={
                "primary_project_id": "demo-project",
                "neighbor_project_ids": ["neighbor-project"],
                "goal_md": "Decide how to refactor the loader.",
                "case_mode": "architecture-decision",
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        case_id = body["case"]["id"]
        assert body["case"]["primary_project_id"] == "demo-project"
        assert {target["relation"] for target in body["targets"]} == {"primary", "neighbor"}
        bundle_path = ai_cases.bundle_file_path(storage.data_dir, case_id)
        assert bundle_path.exists()
        bundle = ai_cases.load_bundle(storage.data_dir, case_id)
        assert bundle.primary_project_id == "demo-project"
        assert bundle.neighbor_project_ids == ["neighbor-project"]


@git_required
@posix_only
def test_run_case_creates_isolated_worktree_and_launches_lead(tmp_path: Path) -> None:
    _app, client, storage, _pm = _harness(tmp_path)
    script = tmp_path / "lead.sh"
    script.write_text("#!/usr/bin/env bash\necho lead-started\nsleep 1\n", encoding="utf-8")
    script.chmod(0o755)

    with client as c:
        created = c.post(
            "/api/v1/ai-cases",
            json={
                "primary_project_id": "demo-project",
                "goal_md": "Research the repo and stage a verdict.",
                "case_mode": "repo-research",
            },
        )
        case_id = created.json()["case"]["id"]
        launched = c.post(
            f"/api/v1/ai-cases/{case_id}/run",
            json={"preferred_runtime": str(script), "open_in_tab": False},
        )
        assert launched.status_code == 200, launched.text
        payload = launched.json()
        detail = payload["case"]
        assert detail["case"]["status"] == "running"
        worktree_path = Path(detail["case"]["worktree_path"])
        assert worktree_path.exists()
        assert worktree_path != Path(c.get("/api/v1/projects/demo-project").json()["path"])
        assert (worktree_path / ".git").exists()
        assert payload["session"]["work_item_id"]
        stopped = c.post(f"/api/v1/ai-cases/{case_id}/stop")
        assert stopped.status_code == 200, stopped.text


def test_run_case_with_ui_policies_opens_quality_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client, _storage, _pm = _harness(tmp_path)
    _patch_fake_spawn(monkeypatch, app)
    with client as c:
        created = c.post(
            "/api/v1/ai-cases",
            json={
                "primary_project_id": "demo-project",
                "goal_md": "Fix the shell and prove the launch path works.",
                "case_mode": "repair",
                "policies": {
                    "quality_profile_id": "quality-critical-ui",
                    "review_policy_id": "review-ui-blocking",
                    "evidence_policy_id": "evidence-browser-proof",
                },
            },
        )
        assert created.status_code == 201, created.text
        case_id = created.json()["case"]["id"]

        launched = c.post(
            f"/api/v1/ai-cases/{case_id}/run",
            json={"preferred_runtime": "codex", "open_in_tab": False},
        )
        assert launched.status_code == 200, launched.text
        payload = launched.json()
        assert len(payload["opened_gates"]) >= 3
        listed = c.get("/api/v1/quality-gates", params={"subject_type": "ai_case", "subject_id": case_id})
        assert listed.status_code == 200, listed.text
        assert len(listed.json()["gates"]) >= 3


def test_export_case_creates_records_and_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _app, client, storage, _pm = _harness(tmp_path)
    preset_dir = tmp_path / "quick-actions"
    preset_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(routes_ai_cases, "bundled_quick_actions_dir", lambda: preset_dir)
    with client as c:
        created = c.post(
            "/api/v1/ai-cases",
            json={
                "primary_project_id": "demo-project",
                "goal_md": "Choose the safer loader plan.",
                "case_mode": "architecture-decision",
            },
        )
        case_id = created.json()["case"]["id"]
        bundle = ai_cases.load_bundle(storage.data_dir, case_id)
        bundle.verdict.summary = "Keep the current loader surface and add a thinner adapter."
        bundle.verdict.chosen_direction = "Adapter over rewrite"
        bundle.verdict.rationale = "Lower blast radius, fewer contract changes."
        bundle.minority_report.strongest_losing_argument = "A rewrite would remove old branching."
        bundle.blast_radius.touched_areas = ["daemon loader", "project bootstrap"]
        bundle.handoff_pack.first_steps = ["Add adapter layer", "Write regression tests"]
        bundle.handoff_pack.unresolved_questions = ["Should the adapter own config validation?"]
        ai_cases.write_bundle(storage.data_dir, bundle)

        adr = c.post(f"/api/v1/ai-cases/{case_id}/export/adr")
        assert adr.status_code == 200, adr.text
        assert adr.json()["created"]

        backlog = c.post(f"/api/v1/ai-cases/{case_id}/export/backlog")
        assert backlog.status_code == 200, backlog.text
        assert backlog.json()["created"]

        memory = c.post(f"/api/v1/ai-cases/{case_id}/export/memory")
        assert memory.status_code == 200, memory.text
        memory_path = Path(memory.json()["path"])
        assert memory_path.exists()
        assert "Adapter over rewrite" in memory_path.read_text(encoding="utf-8")

        preset = c.post(f"/api/v1/ai-cases/{case_id}/export/preset")
        assert preset.status_code == 200, preset.text
        preset_path = Path(preset.json()["path"])
        assert preset_path.exists()
        preset_path.unlink()


def test_open_ai_os_route_registers_managed_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _app, client, _storage, pm = _harness(tmp_path)
    launched: dict[str, str] = {}

    async def _fake_launch(project_id: str, *_, **__) -> None:
        launched["project_id"] = project_id

    monkeypatch.setattr(pm, "launch", _fake_launch)
    with client as c:
        res = c.post("/api/v1/projects/demo-project/open-ai-os")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["app_project_id"] == "ai-operating-system"
        assert body["url"].startswith("http://127.0.0.1:4312/")
        assert launched["project_id"] == "ai-operating-system"
        created = c.get("/api/v1/projects/ai-operating-system")
        assert created.status_code == 200, created.text


def test_open_ai_os_route_accepts_benchmark_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _app, client, _storage, pm = _harness(tmp_path)

    async def _fake_launch(project_id: str, *_, **__) -> None:
        return None

    monkeypatch.setattr(pm, "launch", _fake_launch)
    with client as c:
        res = c.post(
            "/api/v1/projects/demo-project/open-ai-os",
            json={"benchmark_run_id": "bench-123"},
        )
        assert res.status_code == 200, res.text
        assert "benchmark_run_id=bench-123" in res.json()["url"]


def test_install_ai_bundle_registers_assets_and_quick_action(
    tmp_path: Path,
) -> None:
    _app, client, storage, _pm = _harness(tmp_path)
    with client as c:
        installed = c.post("/api/v1/ai-bundles/install/deep-research-council")
        assert installed.status_code == 200, installed.text
        catalog = c.get("/api/v1/ai-bundles")
        actions = c.get("/api/v1/quick-actions")
        profile = c.get("/api/v1/profile/catalog-state")
    assert "deep-research-council" in catalog.json()["installed_ids"]
    assert any(item["id"] == "deep-research-council" for item in actions.json()["actions"])
    profile_items = {item["item_key"]: item for item in profile.json()["items"]}
    assert profile_items["bundle:deep-research-council"]["installed_here"] is True
    assert storage.conn.execute(
        "SELECT 1 FROM agent_role_templates WHERE id = ?",
        ("contract-prosecutor",),
    ).fetchone() is not None


def test_benchmark_run_spawns_candidate_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, storage, _pm = _harness(tmp_path)
    _patch_fake_spawn(monkeypatch, app)
    with client as c:
        c.post("/api/v1/ai-bundles/install/fullstack-app-factory")
        created = c.post(
            "/api/v1/ai-cases",
            json={
                "primary_project_id": "demo-project",
                "goal_md": "Generate the best candidate app.",
                "case_mode": "benchmark",
                "selected_recipe_id": "fullstack-factory-board",
                "intent": {"goal_md": "Generate the best candidate app."},
                "targets": {"primary_project_id": "demo-project"},
                "directives": {
                    "selected_recipe_id": "fullstack-factory-board",
                    "candidate_recipe_ids": ["research-cockpit-v1", "repo-rescue-console"],
                },
            },
        )
        case_id = created.json()["case"]["id"]
        launched = c.post(f"/api/v1/ai-cases/{case_id}/run", json={"open_in_tab": False})
        assert launched.status_code == 200, launched.text
        graph = c.get(f"/api/v1/ai-cases/{case_id}/graph").json()
        bundle = ai_cases.load_bundle(storage.data_dir, case_id)
    assert len(graph["nodes"]) >= 3
    assert len(bundle.candidate_leaderboard) >= 2


def test_portfolio_run_spawns_sequenced_child_slices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, storage, _pm = _harness(tmp_path)
    _patch_fake_spawn(monkeypatch, app)
    with client as c:
        created = c.post(
            "/api/v1/ai-cases",
            json={
                "primary_project_id": "demo-project",
                "neighbor_project_ids": ["neighbor-project"],
                "goal_md": "Map the system boundary and sequence the repo work.",
                "case_mode": "portfolio",
            },
        )
        case_id = created.json()["case"]["id"]
        launched = c.post(f"/api/v1/ai-cases/{case_id}/run", json={"open_in_tab": False})
        assert launched.status_code == 200, launched.text
        graph = c.get(f"/api/v1/ai-cases/{case_id}/graph").json()
        bundle = ai_cases.load_bundle(storage.data_dir, case_id)
    assert len(graph["nodes"]) >= 3
    assert any(card.project_id == "neighbor-project" for card in bundle.claim_cards)


def test_challenge_and_harvest_modes_gain_specialized_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, storage, _pm = _harness(tmp_path)
    _patch_fake_spawn(monkeypatch, app)
    with client as c:
        challenge = c.post(
            "/api/v1/ai-cases",
            json={
                "primary_project_id": "demo-project",
                "goal_md": "Challenge this proposed direction.",
                "case_mode": "challenge",
            },
        )
        challenge_id = challenge.json()["case"]["id"]
        challenge_run = c.post(f"/api/v1/ai-cases/{challenge_id}/run", json={"open_in_tab": False})
        assert challenge_run.status_code == 200, challenge_run.text
        challenge_graph = c.get(f"/api/v1/ai-cases/{challenge_id}/graph").json()
        challenge_bundle = ai_cases.load_bundle(storage.data_dir, challenge_id)

        harvest = c.post(
            "/api/v1/ai-cases",
            json={
                "primary_project_id": "demo-project",
                "goal_md": "Harvest reusable ideas from references.",
                "case_mode": "harvest",
                "intent": {"goal_md": "Harvest reusable ideas from references."},
                "targets": {
                    "primary_project_id": "demo-project",
                    "reference_urls": ["https://example.com/reference-a", "https://example.com/reference-b"],
                },
            },
        )
        harvest_id = harvest.json()["case"]["id"]
        harvest_run = c.post(f"/api/v1/ai-cases/{harvest_id}/run", json={"open_in_tab": False})
        assert harvest_run.status_code == 200, harvest_run.text
        harvest_bundle = ai_cases.load_bundle(storage.data_dir, harvest_id)
        harvest_case = c.get(f"/api/v1/ai-cases/{harvest_id}").json()

    assert len(challenge_graph["nodes"]) >= 2
    assert len(challenge_bundle.failure_matrix) >= 3
    assert len(challenge_bundle.contradiction_docket) >= 1
    assert len(harvest_bundle.promotions) >= 2
    assert len(harvest_case["case"]["targets"]["attached_source_ids"]) >= 2
