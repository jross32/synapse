"""Security and dry-run HTTP contract for local Storage Manager."""
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from synapse_daemon.errors import SynapseError
from fastapi.testclient import TestClient
from synapse_daemon.routes_hybrid_storage import build_hybrid_storage_router


class StubAuth:
    device_cookie_name = "synapse_device"

    def subject_for_token(self, token):
        if token == "owner":
            return SimpleNamespace(kind="local")
        if token == "worker":
            return SimpleNamespace(kind="worker", project_id="test", session_id=None, authority=None)
        return None


def make_client(root):
    app = FastAPI()
    @app.exception_handler(SynapseError)
    async def synapse_error_handler(request, exc):
        return JSONResponse(status_code=exc.status, content={"error": str(exc)})
    app.include_router(build_hybrid_storage_router(StubAuth(), root))
    return TestClient(app)


def test_storage_endpoints_require_auth(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/storage-manager/providers").status_code == 401
        assert client.get("/storage-manager/providers", headers={"X-Synapse-Token": "worker"}).status_code == 403
        response = client.get("/storage-manager/providers", headers={"X-Synapse-Token": "owner"})
        assert response.status_code == 200
        assert response.json()["cloud_mutations_enabled"] is False
        assert all(p.get("account_bound") is False for p in response.json()["providers"] if p["id"] != "local")


def test_inventory_dry_run_and_path_isolation(tmp_path):
    allowed = tmp_path / "allowed"
    forbidden = tmp_path / "private"
    allowed.mkdir()
    forbidden.mkdir()
    (allowed / "archive.zip").write_bytes(b"abcdefghij")
    with make_client(allowed) as client:
        headers = {"X-Synapse-Token": "owner"}
        data = {"project_path": str(allowed)}
        scan = client.post("/storage-manager/inventory", json=data, headers=headers)
        assert scan.status_code == 200
        assert scan.json()["read_only"] is True
        preview = client.post("/storage-manager/migration-preview", json={**data, "min_size_bytes": 5}, headers=headers)
        assert preview.status_code == 200
        assert preview.json()["potential_reclaim_bytes"] == 10
        assert preview.json()["local_files_removed"] is False
        assert (allowed / "archive.zip").exists()
        denied = client.post("/storage-manager/inventory", json={"project_path": str(forbidden)}, headers=headers)
        assert denied.status_code == 403
