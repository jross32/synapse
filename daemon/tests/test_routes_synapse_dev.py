"""Tests for gated Synapse self-improvement routes."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus
import synapse_daemon.synapse_dev as synapse_dev_module


def _harness(tmp_path: Path) -> tuple[TestClient, Storage]:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token}), storage


def test_synapse_dev_routes_refuse_when_disabled(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    response = client.post("/api/v1/synapse-dev/test/full")
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "synapse_dev.disabled"


def test_synapse_dev_full_test_updates_health_report(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SYNAPSE_DEV_ENABLED", "1")

    def fake_command(command: list[str], *, cwd: Path, log_path: Path) -> dict[str, object]:
        joined = " ".join(command)
        if "pytest" in joined:
            return {
                "ok": True,
                "returncode": 0,
                "stdout": "2 passed, 1 skipped in 0.12s",
                "stderr": "",
                "combined": "2 passed, 1 skipped in 0.12s",
                "duration_s": 0.12,
                "log_path": str(log_path),
            }
        return {
            "ok": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "combined": "",
            "duration_s": 0.08,
            "log_path": str(log_path),
        }

    monkeypatch.setattr(synapse_dev_module, "_command_result", fake_command)
    client, _ = _harness(tmp_path)
    response = client.post("/api/v1/synapse-dev/test/full")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["pytest"]["passed"] == 2
    assert payload["pytest"]["skipped"] == 1
    assert payload["tsc"]["ok"] is True

    health = client.get("/api/v1/ai/health-report")
    assert health.status_code == 200, health.text
    body = health.json()
    assert body["tests"]["last_run_ok"] is True
    assert body["tests"]["passed"] == 2
    assert body["git"]["synapse_dev_enabled"] is True


def test_synapse_dev_file_test_validates_path_safety(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SYNAPSE_DEV_ENABLED", "1")
    client, _ = _harness(tmp_path)
    response = client.post(
        "/api/v1/synapse-dev/test/file",
        json={"path": "../outside.py"},
    )
    assert response.status_code == 422, response.text
    assert "daemon/tests" in response.json()["message"]
