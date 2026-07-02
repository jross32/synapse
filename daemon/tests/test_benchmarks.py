from __future__ import annotations

import sys
from dataclasses import dataclass
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


@dataclass
class _FakeSummary:
    session_id: str
    argv: list[str]
    cwd: str | None
    started_at: str
    exit_code: int | None
    rows: int
    cols: int
    project_id: str | None = None


class _FakeSession:
    def __init__(self, session_id: str, argv: list[str], cwd: str | None, project_id: str | None) -> None:
        self.session_id = session_id
        self.argv = argv
        self.cwd = cwd
        self.project_id = project_id

    def summary(self) -> _FakeSummary:
        return _FakeSummary(
            session_id=self.session_id,
            argv=self.argv,
            cwd=self.cwd,
            started_at="2026-06-28T00:00:00+00:00",
            exit_code=None,
            rows=24,
            cols=80,
            project_id=self.project_id,
        )


def test_benchmark_run_launches_thread_surface(tmp_path: Path) -> None:
    app, client, _storage = _harness(tmp_path)

    async def fake_spawn(argv, cwd=None, env=None, rows=24, cols=80, project_id=None, session_id=None):
        return _FakeSession("sess-bench", argv, cwd, project_id)

    app.state.pty_manager.spawn = fake_spawn

    with client as c:
        created = c.post(
            "/api/v1/benchmarks/runs",
            json={
                "spec_id": "coder-workspace-v1",
                "project_id": "demo-project",
                "title": "Thread benchmark",
                "repeat_count": 1,
                "matrix": [
                    {
                        "scenario_id": "static-app-mini",
                        "runtime_id": "python",
                        "provider": "test",
                        "model": "python",
                        "surface_kind": "synapse_coder_thread",
                        "argv": [sys.executable, "-V"],
                    }
                ],
            },
        )
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]

        launched = c.post(f"/api/v1/benchmarks/runs/{run_id}/launch", json={})
        assert launched.status_code == 200, launched.text
        body = launched.json()
        assert body["session"]["session_id"] == "sess-bench"
        assert body["thread_id"]
        assert body["coder_run_id"]
        assert Path(body["prompt_path"]).exists()

        report = c.get(f"/api/v1/benchmarks/runs/{run_id}").json()
        attempt = report["report"]["all_attempts"][0]
        assert attempt["thread_id"] == body["thread_id"]
        assert attempt["coder_run_id"] == body["coder_run_id"]
        assert attempt["surface_kind"] == "synapse_coder_thread"


def test_direct_ingest_rescore_and_export(tmp_path: Path) -> None:
    _app, client, _storage = _harness(tmp_path)
    with client as c:
        created = c.post(
            "/api/v1/benchmarks/runs",
            json={
                "spec_id": "coder-workspace-v1",
                "project_id": "demo-project",
                "title": "Direct benchmark",
                "repeat_count": 1,
                "matrix": [
                    {
                        "scenario_id": "repo-fix-mini",
                        "runtime_id": "codex",
                        "provider": "openai",
                        "model": "codex",
                        "surface_kind": "direct_cli",
                    }
                ],
            },
        )
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]
        initial = c.get(f"/api/v1/benchmarks/runs/{run_id}").json()
        attempt_id = initial["report"]["all_attempts"][0]["id"]

        ingested = c.post(
            "/api/v1/benchmarks/ingest-direct",
            json={
                "attempt_id": attempt_id,
                "actual_runtime_id": "codex",
                "status": "ingested",
                "elapsed_seconds": 120,
                "input_tokens": 200,
                "output_tokens": 100,
                "total_tokens": 300,
                "token_provenance": "estimated",
                "token_source": "transcript_estimator",
                "quality_score_100": 84,
                "objective_pass_rate": 0.8,
                "rubric_score_100": 88,
                "verifier_summary": {"checks_passed": 4},
                "artifacts": [
                    {
                        "kind": "verifier-output",
                        "label": "Verifier summary",
                        "path": str(tmp_path / "verifier.txt"),
                        "mime": "text/plain",
                    }
                ],
            },
        )
        assert ingested.status_code == 200, ingested.text
        assert ingested.json()["attempt"]["quality_per_1k_tokens"] is not None

        rescored = c.post(f"/api/v1/benchmarks/runs/{run_id}/rescore")
        assert rescored.status_code == 200, rescored.text
        report = rescored.json()["report"]
        assert report["official_quality_ranking"][0]["candidate_key"].startswith("direct_cli")
        assert report["strict_comparable_attempt_ids"] == [attempt_id]

        exported = c.post(f"/api/v1/benchmarks/runs/{run_id}/export")
        assert exported.status_code == 200, exported.text
        paths = exported.json()
        assert Path(paths["json_path"]).exists()
        assert Path(paths["md_path"]).exists()
        assert Path(paths["lessons_path"]).exists()
