"""Release authority boundaries without starting builds or external publication."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from synapse_daemon.auth import TokenSubject, _enforce_worker_scope, require_token
from synapse_daemon.errors import SynapseError
from synapse_daemon.release_pipeline import ReleasePipeline
from synapse_daemon.routes_release_pipeline import build_release_pipeline_router
from synapse_daemon.storage import Storage


RUN_ID = "a" * 32


def worker_request(method: str, suffix: str) -> Request:
    return Request({
        "type": "http", "method": method,
        "path": "/api/v1/release-pipeline" + suffix,
        "headers": [(b"x-synapse-session", b"release-worker")],
        "query_string": b"",
    })


@pytest.mark.parametrize("method,suffix", [
    ("POST", ""), ("PUT", "/publisher"), ("POST", "/" + RUN_ID + "/start"),
    ("POST", "/" + RUN_ID + "/resume"), ("POST", "/" + RUN_ID + "/proof"),
    ("POST", "/" + RUN_ID + "/request-publication"),
    ("POST", "/" + RUN_ID + "/publish"), ("POST", "/" + RUN_ID + "/verify-live"),
])
def test_workspace_worker_cannot_mutate_global_release_pipeline(method, suffix):
    subject = TokenSubject(kind="worker", session_id="release-worker",
                           project_id="assigned-workspace", authority="workspace")
    with pytest.raises(SynapseError) as error:
        _enforce_worker_scope(worker_request(method, suffix), subject)
    assert error.value.status == 403
    assert error.value.envelope.code == "auth.worker_scope_denied"


@pytest.mark.parametrize("suffix", ["", "/" + RUN_ID, "/" + RUN_ID + "/plan"])
def test_workspace_worker_can_read_release_discovery(suffix):
    subject = TokenSubject(kind="worker", session_id="release-worker",
                           project_id="assigned-workspace", authority="workspace")
    _enforce_worker_scope(worker_request("GET", suffix), subject)


def test_owner_dispatches_request_start_publish_but_worker_never_reaches_executor(tmp_path, monkeypatch):
    """Real router/dependency accepts owner; arbitrary-source worker request is denied."""
    calls = []
    for name in ("request", "start", "publish"):
        def operation(self, *args, _name=name):
            calls.append((_name, args))
            return {"id": RUN_ID, "status": "fixture"}
        monkeypatch.setattr(ReleasePipeline, name, operation)

    subjects = {
        "owner": TokenSubject(kind="local"),
        "worker": TokenSubject(kind="worker", session_id="release-worker",
                               project_id="assigned-workspace", authority="workspace"),
    }
    auth = SimpleNamespace(device_cookie_name="synapse-device-token",
                           subject_for_token=lambda token: subjects.get(token))
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    try:
        developer = SimpleNamespace(repo_root=tmp_path, enabled=lambda: True)
        app = FastAPI()
        async def publish(_event, _payload):
            return None
        app.state.bus = SimpleNamespace(publish=publish)
        @app.exception_handler(SynapseError)
        async def synapse_error(_request, error):
            return JSONResponse(error.envelope.model_dump(), status_code=error.status)
        app.include_router(build_release_pipeline_router(storage, developer),
                           prefix="/api/v1", dependencies=[Depends(require_token(auth))])
        client = TestClient(app)
        payload = {"version": "1.2.3", "source_root": str(tmp_path / "outside-assigned-project"),
                   "publish_requested": True}
        worker_headers = {"X-Synapse-Token": "worker", "X-Synapse-Session": "release-worker"}
        for path, body in [
            ("/api/v1/release-pipeline", payload),
            (f"/api/v1/release-pipeline/{RUN_ID}/start", {}),
            (f"/api/v1/release-pipeline/{RUN_ID}/publish", {}),
        ]:
            assert client.post(path, json=body, headers=worker_headers).status_code == 403
        assert calls == []

        owner_headers = {"X-Synapse-Token": "owner"}
        assert client.post("/api/v1/release-pipeline", json=payload, headers=owner_headers).status_code == 201
        assert client.post(f"/api/v1/release-pipeline/{RUN_ID}/start", headers=owner_headers).status_code == 200
        assert client.post(f"/api/v1/release-pipeline/{RUN_ID}/publish", headers=owner_headers).status_code == 200
        assert [name for name, _args in calls] == ["request", "start", "publish"]
        assert client.get("/api/v1/release-pipeline", headers=worker_headers).status_code == 200
    finally:
        storage.close()
