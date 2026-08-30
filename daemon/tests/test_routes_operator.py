from fastapi import FastAPI
from fastapi.testclient import TestClient
from synapse_daemon.routes_operator import build_operator_router
from synapse_daemon.storage import Storage


def test_operator_plan_route_returns_small_auditable_plan(tmp_path):
    storage = Storage(tmp_path)
    storage.open()
    try:
        app = FastAPI()
        app.include_router(build_operator_router(storage), prefix="/api/v1")
        client = TestClient(app)

        response = client.post(
            "/api/v1/operator/plan",
            json={
                "intent": "Fix the app timeout and verify it",
                "capabilities": ["trace", "watchdog", "project_doctor", "synapse", "reflex"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "diagnose"
        assert [step["capability"] for step in body["steps"]] == ["trace", "watchdogs", "project_doctor", "shell", "desktop"]
        assert body["missing_capabilities"] == []
        assert body["capability_source"] == "request"
    finally:
        storage.close()


def test_operator_plan_route_uses_synapse_native_capabilities_when_omitted(tmp_path):
    storage = Storage(tmp_path)
    storage.open()
    try:
        app = FastAPI()
        app.include_router(build_operator_router(storage), prefix="/api/v1")
        client = TestClient(app)
        response = client.post("/api/v1/operator/plan", json={"intent": "monitor system health"})
        assert response.status_code == 200
        body = response.json()
        assert body["capability_source"] == "synapse"
        assert body["mode"] == "observe"
        assert "trace" in body["available_capabilities"]
        assert "watchdogs" in body["available_capabilities"]
        assert "project_doctor" in body["available_capabilities"]
    finally:
        storage.close()
