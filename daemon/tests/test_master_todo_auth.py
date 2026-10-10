from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.testclient import TestClient
from synapse_daemon.routes_master_todo import build_master_todo_router


def test_planner_guard_and_persistence(tmp_path):
    def guard(x_synapse_token: str | None = Header(None)):
        if x_synapse_token != "test-token":
            raise HTTPException(401, "Unauthorized")

    app = FastAPI()
    app.include_router(build_master_todo_router(tmp_path), prefix="/api/v1", dependencies=[Depends(guard)])
    client = TestClient(app)
    url = "/api/v1/master-todo"
    assert client.get(url).status_code == 401
    headers = {"X-Synapse-Token": "test-token"}
    assert client.get(url, headers=headers).status_code == 200
    result = client.post(url, headers=headers, json={"action": "complete", "task_id": "001", "event_id": "first"})
    assert result.status_code == 200
    assert client.get(url, headers=headers).json()["tasks"][0]["status"] == "done"
