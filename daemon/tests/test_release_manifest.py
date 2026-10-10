"""Release listing and downloads must agree, be authenticated and be allowlisted."""
from __future__ import annotations

import hashlib
import importlib
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon import __version__
from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

manifest_module = importlib.import_module("synapse_daemon.release_manifest")
routes_module = importlib.import_module("synapse_daemon.routes_about")


@contextmanager
def _client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(manifest_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(routes_module, "repo_root", lambda: tmp_path)
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    with TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token}) as client:
        yield client


def test_releases_missing_are_planned_and_unservable(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/api/v1/about/releases")
        assert response.status_code == 200
        artifacts = response.json()["artifacts"]
        assert len(artifacts) == 3
        assert all(item["status"] == "planned" and item["download_url"] is None for item in artifacts)
        missing = client.get(f"/api/v1/about/download/Synapse Setup {__version__}.exe")
        assert missing.status_code == 404


def test_allowlisted_artifact_hash_and_download(tmp_path: Path, monkeypatch):
    release = tmp_path / "release"
    release.mkdir()
    filename = f"Synapse Setup {__version__}.exe"
    payload = b"synthetic fixture for test, not an executable"
    (release / filename).write_bytes(payload)
    (release / "private.txt").write_text("never expose")

    with _client(tmp_path, monkeypatch) as client:
        artifact = client.get("/api/v1/about/releases").json()["artifacts"][0]
        assert artifact["status"] == "ready"
        assert artifact["size_bytes"] == len(payload)
        assert artifact["sha256"] == hashlib.sha256(payload).hexdigest()
        assert artifact["filename"] == filename
        assert artifact["download_url"].endswith(filename)

        response = client.get(artifact["download_url"])
        assert response.status_code == 200
        assert response.content == payload
        assert "attachment" in response.headers["content-disposition"].lower()
        assert client.get("/api/v1/about/download/private.txt").status_code == 404

        # A nested TestClient may stall during Windows shutdown; reuse the portal.
        assert client.get(artifact["download_url"], headers={"X-Synapse-Token": ""}).status_code == 401


def test_empty_artifact_is_not_published(tmp_path: Path, monkeypatch):
    release = tmp_path / "release"
    release.mkdir()
    (release / f"Synapse Setup {__version__}.exe").write_bytes(b"")

    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/api/v1/about/releases").json()["artifacts"][0]["status"] == "planned"
