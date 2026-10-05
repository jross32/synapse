"""REST contract tests for Synapse Video Studio."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _client(tmp_path: Path) -> tuple[TestClient, str, Path]:
    root = tmp_path / "project"
    root.mkdir()
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(conn, Project(id="demo", name="Demo", path=str(root), launch_cmd="echo hi"))
    app = build_app(storage, EventBus())
    return TestClient(app), app.state.auth.local_token, root


def _headers(token: str) -> dict[str, str]:
    return {"X-Synapse-Token": token}


def test_status_and_plan_roundtrip(tmp_path: Path, monkeypatch) -> None:
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    client, token, _ = _client(tmp_path)

    status = client.get("/api/v1/video-generation/status", headers=_headers(token))
    assert status.status_code == 200
    assert status.json()["supports"]["max_video_seconds"] == 300

    created = client.post(
        "/api/v1/video-generation/plans",
        headers=_headers(token),
        json={
            "project_id": "demo",
            "title": "Tiny story",
            "brief": "Same character moves from outside to inside.",
            "audio_mode": "native",
            "character_bible": "Alex keeps the same face, coat, and voice.",
            "shots": [
                {
                    "prompt": "Alex walks to the door.",
                    "duration_seconds": 8,
                    "continuity_group": "door",
                    "audio_cues": "Rain and footsteps.",
                },
                {
                    "prompt": "Alex opens the door and enters.",
                    "duration_seconds": 8,
                    "continuity_group": "door",
                    "dialogue": "I'm home.",
                },
            ],
        },
    )
    assert created.status_code == 200, created.text
    plan = created.json()
    assert plan["planned_duration_seconds"] == 16

    got = client.get(
        f"/api/v1/video-generation/projects/demo/plans/{plan['plan_id']}",
        headers=_headers(token),
    )
    assert got.status_code == 200
    assert got.json()["shots"][1]["dialogue"] == "I'm home."


def test_google_credential_is_encrypted_at_rest_and_status_never_returns_secret(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    client, token, _ = _client(tmp_path)
    secret = "test-google-video-secret-value"

    response = client.put(
        "/api/v1/video-generation/credentials/google",
        headers=_headers(token),
        json={"api_key": secret},
    )
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert secret not in response.text

    status = client.get("/api/v1/video-generation/status", headers=_headers(token))
    assert status.status_code == 200
    assert status.json()["providers"]["google"]["configured"] is True
    assert secret not in status.text

    db = client.app.state.storage.conn
    raw = db.execute("SELECT value_json FROM settings WHERE key='video.google_api_key'").fetchone()["value_json"]
    assert secret not in raw

    cleared = client.delete(
        "/api/v1/video-generation/credentials/google",
        headers=_headers(token),
    )
    assert cleared.status_code == 200
    assert cleared.json()["configured"] is False
