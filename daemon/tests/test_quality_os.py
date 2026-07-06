from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> TestClient:
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
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def test_quality_os_routes_expose_seeded_surfaces_and_contracts(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        surfaces = c.get("/api/v1/ui-surface-map")
        assert surfaces.status_code == 200, surfaces.text
        surface_ids = {surface["id"] for surface in surfaces.json()["surfaces"]}
        assert "apps.projects-grid" in surface_ids
        assert "shared.project-target-picker" in surface_ids

        contracts = c.get("/api/v1/ui-contracts")
        assert contracts.status_code == 200, contracts.text
        contract_ids = {contract["id"] for contract in contracts.json()["contracts"]}
        assert "project-launch-action" in contract_ids
        assert "project-detail-close-button" in contract_ids


def test_contract_run_opens_and_resolves_quality_gate(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        failed = c.post(
            "/api/v1/ui-contracts/project-detail-close-button/run",
            json={
                "subject_type": "ai_case",
                "subject_id": "case-123",
                "verdict": "fail",
                "label": "Close button failed in browser proof",
                "artifact_path": str(tmp_path / "close-button.png"),
            },
        )
        assert failed.status_code == 200, failed.text
        gate = failed.json()["gate"]
        assert gate["status"] == "open"
        assert gate["gate_kind"] == "critical-ui"

        passed = c.post(
            "/api/v1/ui-contracts/project-detail-close-button/run",
            json={
                "subject_type": "ai_case",
                "subject_id": "case-123",
                "gate_id": gate["id"],
                "verdict": "pass",
                "label": "Close button passed after fix",
                "artifact_path": str(tmp_path / "close-button-fixed.png"),
            },
        )
        assert passed.status_code == 200, passed.text
        cleared = c.get(f"/api/v1/quality-gates/{gate['id']}")
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["status"] == "passed"


def test_repeated_failure_keeps_one_open_gate(tmp_path: Path) -> None:
    # Regression: several bug-hunters/personas hitting the SAME broken surface
    # must accumulate on one open gate, not churn a fresh gate each time.
    client = _harness(tmp_path)
    with client as c:
        first = c.post(
            "/api/v1/ui-contracts/project-detail-close-button/run",
            json={"subject_type": "ai_case", "subject_id": "case-dup", "verdict": "fail", "label": "hunter A"},
        )
        assert first.status_code == 200, first.text
        gate1 = first.json()["gate"]
        assert gate1["status"] == "open"

        second = c.post(
            "/api/v1/ui-contracts/project-detail-close-button/run",
            json={"subject_type": "ai_case", "subject_id": "case-dup", "verdict": "fail", "label": "hunter B (same surface)"},
        )
        assert second.status_code == 200, second.text
        gate2 = second.json()["gate"]
        # One bug -> one gate: the second failure returns the SAME still-open gate.
        assert gate2["id"] == gate1["id"]
        assert gate2["status"] == "open"
        assert c.get(f"/api/v1/quality-gates/{gate1['id']}").json()["status"] == "open"


def test_evidence_records_whether_artifact_screenshot_exists(tmp_path: Path) -> None:
    # Evidence honesty: a "browser-proof" screenshot path is checked at record time
    # so consumers can trust the proof exists (absolute paths only).
    client = _harness(tmp_path)
    with client as c:
        real = tmp_path / "real-shot.png"
        real.write_bytes(b"\x89PNG\r\n")
        present = c.post(
            "/api/v1/ui-contracts/project-detail-close-button/run",
            json={"subject_type": "ai_case", "subject_id": "case-art-present", "verdict": "fail", "artifact_path": str(real)},
        )
        assert present.status_code == 200, present.text
        assert present.json()["evidence"]["metadata"]["artifact_present"] is True

        missing = c.post(
            "/api/v1/ui-contracts/project-detail-close-button/run",
            json={"subject_type": "ai_case", "subject_id": "case-art-missing", "verdict": "fail", "artifact_path": str(tmp_path / "nope.png")},
        )
        assert missing.status_code == 200, missing.text
        assert missing.json()["evidence"]["metadata"]["artifact_present"] is False


def test_impact_audit_can_open_blocking_contract_gates(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        audited = c.post(
            "/api/v1/ui-impact-audit",
            json={
                "file_paths": ["renderer/components/ProjectTile.tsx"],
                "subject_type": "benchmark_attempt",
                "subject_id": "attempt-123",
                "open_gates": True,
                "blocking_only": True,
            },
        )
        assert audited.status_code == 200, audited.text
        body = audited.json()
        contract_ids = {contract["id"] for contract in body["contracts"]}
        assert "project-launch-action" in contract_ids
        assert body["created_gates"]
        assert any(gate["blocking"] for gate in body["created_gates"])


def test_benchmark_export_blocked_until_attempt_gate_is_resolved(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        created = c.post(
            "/api/v1/benchmarks/runs",
            json={
                "spec_id": "coder-workspace-v1",
                "project_id": "demo-project",
                "title": "Blocked benchmark export",
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
        attempt_id = c.get(f"/api/v1/benchmarks/runs/{run_id}").json()["report"]["all_attempts"][0]["id"]
        ingest = c.post(
            "/api/v1/benchmarks/ingest-direct",
            json={
                "attempt_id": attempt_id,
                "actual_runtime_id": "codex",
                "status": "ingested",
                "elapsed_seconds": 30,
                "total_tokens": 200,
                "token_provenance": "estimated",
                "token_source": "transcript_estimator",
                "quality_score_100": 80,
                "objective_pass_rate": 0.8,
                "rubric_score_100": 82,
            },
        )
        assert ingest.status_code == 200, ingest.text

        gate = c.post(
            "/api/v1/quality-gates",
            json={
                "subject_type": "benchmark_attempt",
                "subject_id": attempt_id,
                "gate_kind": "critical-ui",
                "title": "Launch path still unverified",
                "blocking": True,
            },
        )
        assert gate.status_code == 201, gate.text

        blocked = c.post(f"/api/v1/benchmarks/runs/{run_id}/export")
        assert blocked.status_code == 422, blocked.text

        cleared = c.post(
            f"/api/v1/quality-gates/{gate.json()['id']}/resolve",
            json={"status": "passed", "resolved_by": "test"},
        )
        assert cleared.status_code == 200, cleared.text
        exported = c.post(f"/api/v1/benchmarks/runs/{run_id}/export")
        assert exported.status_code == 200, exported.text


def test_ai_case_export_blocked_until_gate_is_cleared(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        created = c.post(
            "/api/v1/ai-cases",
            json={
                "primary_project_id": "demo-project",
                "goal_md": "Decide the safer fix.",
                "case_mode": "architecture-decision",
            },
        )
        assert created.status_code == 201, created.text
        case_id = created.json()["case"]["id"]

        gate = c.post(
            "/api/v1/quality-gates",
            json={
                "subject_type": "ai_case",
                "subject_id": case_id,
                "gate_kind": "critical-ui",
                "title": "Blocking UI issue still open",
                "blocking": True,
            },
        )
        assert gate.status_code == 201, gate.text

        blocked = c.post(f"/api/v1/ai-cases/{case_id}/export/adr")
        assert blocked.status_code == 422, blocked.text

        cleared = c.post(
            f"/api/v1/quality-gates/{gate.json()['id']}/resolve",
            json={"status": "passed", "resolved_by": "test"},
        )
        assert cleared.status_code == 200, cleared.text
        exported = c.post(f"/api/v1/ai-cases/{case_id}/export/adr")
        assert exported.status_code == 200, exported.text
