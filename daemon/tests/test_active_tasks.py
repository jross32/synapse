from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse_daemon import active_tasks, projects
from synapse_daemon.active_tasks import (
    ActiveTaskCreate,
    ActiveTaskScheduler,
    ActiveTaskUpdate,
    DispatchReceipt,
    ForemanDispatcher,
)
from synapse_daemon.projects import Project
from synapse_daemon.routes_active_tasks import build_active_tasks_router
from synapse_daemon.storage import Storage
from synapse_daemon.time_utils import to_iso, utc_now


class FakeDispatcher:
    def __init__(self):
        self.dispatched = []
        self.active_refs: set[str] = set()

    async def dispatch(self, task, run_id):
        ref = f"campaign-{len(self.dispatched) + 1}"
        self.dispatched.append((task.id, task.project_id, task.preferred_runtime, run_id, ref))
        return DispatchReceipt(ref_id=ref, status="active", detail={"id": ref, "status": "active"})

    async def is_active(self, ref_id):
        return ref_id in self.active_refs


@pytest.fixture()
def storage(tmp_path: Path):
    db = Storage(tmp_path / "data")
    db.open()
    applied = db.migrate()
    assert 42 in db.applied_migration_numbers()
    with db.transaction() as conn:
        projects.create(conn, Project(id="ai-world", name="AI WORLD", path=str(tmp_path / "AI_WORLD"), launch_cmd="python main.py"))
        projects.create(conn, Project(id="stock-hunter", name="Stock Hunter", path=str(tmp_path / "stock"), launch_cmd="python app.py"))
    try:
        yield db
    finally:
        db.close()


def test_synapse_active_tasks_are_not_capped_at_five(storage):
    with storage.transaction() as conn:
        for idx in range(12):
            active_tasks.create_task(
                conn,
                ActiveTaskCreate(
                    project_id="ai-world",
                    name=f"Iteration loop {idx + 1}",
                    interval_seconds=3600,
                ),
            )
    rows = active_tasks.list_tasks(storage.conn, project_id="ai-world")
    assert len(rows) == 12
    assert all(row.enabled for row in rows)


def test_interval_task_is_durable_and_coalesces_missed_slots(storage):
    start = utc_now()
    with storage.transaction() as conn:
        task = active_tasks.create_task(
            conn,
            ActiveTaskCreate(project_id="ai-world", name="Hourly", interval_seconds=3600),
            now=start,
        )
    assert task.next_run_at == to_iso(start + timedelta(hours=1))

    # A daemon that was down for 5h should produce one due task, not five bursts.
    due_at = start + timedelta(hours=5, minutes=7)
    due = active_tasks.due_tasks(storage.conn, due_at)
    assert [row.id for row in due] == [task.id]
    with storage.transaction() as conn:
        active_tasks._advance_schedule(conn, task, start + timedelta(hours=1), due_at)
    fresh = active_tasks.get_task(storage.conn, task.id)
    assert fresh.next_run_at == to_iso(start + timedelta(hours=6))


@pytest.mark.asyncio
async def test_scheduler_dispatches_due_task_and_records_history(storage):
    dispatcher = FakeDispatcher()
    scheduler = ActiveTaskScheduler(storage, dispatcher, poll_seconds=0.05)
    now = utc_now()
    with storage.transaction() as conn:
        task = active_tasks.create_task(
            conn,
            ActiveTaskCreate(
                project_id="ai-world",
                name="Universe realism",
                prompt="Continue the highest-value causal realism improvement.",
                interval_seconds=3600,
                next_run_at=to_iso(now - timedelta(seconds=1)),
                preferred_runtime="chatgpt_web",
            ),
            now=now - timedelta(hours=1),
        )
    runs = await scheduler.run_due(now=now)
    assert len(runs) == 1
    assert runs[0].status.value == "dispatched"
    assert runs[0].dispatch_ref == "campaign-1"
    assert dispatcher.dispatched[0][1] == "ai-world"
    fresh = active_tasks.get_task(storage.conn, task.id)
    assert fresh.run_count == 1
    assert fresh.last_dispatch_ref == "campaign-1"
    assert fresh.next_run_at is not None
    assert active_tasks.list_runs(storage.conn, task.id)[0].dispatch_ref == "campaign-1"


@pytest.mark.asyncio
async def test_no_overlap_skips_when_prior_foreman_campaign_is_still_active(storage):
    dispatcher = FakeDispatcher()
    scheduler = ActiveTaskScheduler(storage, dispatcher)
    now = utc_now()
    with storage.transaction() as conn:
        task = active_tasks.create_task(
            conn,
            ActiveTaskCreate(
                project_id="ai-world",
                name="No collision",
                interval_seconds=3600,
                next_run_at=to_iso(now - timedelta(seconds=1)),
            ),
            now=now - timedelta(hours=1),
        )
        conn.execute(
            "UPDATE active_tasks SET last_dispatch_ref='prior-campaign',last_status='dispatched' WHERE id=?",
            (task.id,),
        )
    dispatcher.active_refs.add("prior-campaign")
    runs = await scheduler.run_due(now=now)
    assert len(runs) == 1
    assert runs[0].status.value == "skipped_overlap"
    assert dispatcher.dispatched == []
    fresh = active_tasks.get_task(storage.conn, task.id)
    assert fresh.run_count == 0
    assert fresh.next_run_at is not None


@pytest.mark.asyncio
async def test_once_and_max_runs_disable_task_after_dispatch(storage):
    dispatcher = FakeDispatcher()
    scheduler = ActiveTaskScheduler(storage, dispatcher)
    now = utc_now()
    with storage.transaction() as conn:
        once = active_tasks.create_task(
            conn,
            ActiveTaskCreate(
                project_id="ai-world",
                name="One shot",
                schedule_kind="once",
                next_run_at=to_iso(now - timedelta(seconds=1)),
                max_runs=1,
            ),
            now=now,
        )
    await scheduler.run_due(now=now)
    fresh = active_tasks.get_task(storage.conn, once.id)
    assert fresh.run_count == 1
    assert fresh.enabled is False
    assert fresh.next_run_at is None


def test_restart_marks_inflight_scheduler_dispatch_interrupted(storage):
    now = utc_now()
    with storage.transaction() as conn:
        task = active_tasks.create_task(conn, ActiveTaskCreate(project_id="ai-world", name="Restart safe"), now=now)
        conn.execute(
            "INSERT INTO active_task_runs(id,task_id,scheduled_for,started_at,status,created_at) VALUES('run1',?,?,?,'running',?)",
            (task.id, to_iso(now), to_iso(now), to_iso(now)),
        )
    with storage.transaction() as conn:
        count = active_tasks.recover_interrupted_runs(conn, now + timedelta(minutes=1))
    assert count == 1
    run = active_tasks.list_runs(storage.conn, task.id)[0]
    assert run.status.value == "interrupted"
    assert "restarted" in run.error.lower()


def test_task_update_pause_resume_and_prompt(storage):
    now = utc_now()
    with storage.transaction() as conn:
        task = active_tasks.create_task(conn, ActiveTaskCreate(project_id="ai-world", name="Loop"), now=now)
        paused = active_tasks.update_task(conn, task.id, ActiveTaskUpdate(enabled=False, prompt="New directive"), now=now)
    assert paused.enabled is False
    assert paused.prompt == "New directive"
    with storage.transaction() as conn:
        resumed = active_tasks.update_task(conn, task.id, ActiveTaskUpdate(enabled=True), now=now)
    assert resumed.enabled is True
    assert resumed.next_run_at is not None


def test_active_tasks_rest_api_and_summary(storage):
    dispatcher = FakeDispatcher()
    scheduler = ActiveTaskScheduler(storage, dispatcher)
    app = FastAPI()
    app.include_router(build_active_tasks_router(storage, scheduler), prefix="/api/v1")
    client = TestClient(app)
    response = client.post(
        "/api/v1/active-tasks",
        json={
            "project_id": "ai-world",
            "name": "AI WORLD continuous development",
            "prompt": "Keep improving the universe.",
            "interval_seconds": 3600,
            "preferred_runtime": "chatgpt_web",
        },
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    assert client.get("/api/v1/active-tasks?project_id=ai-world").json()["count"] == 1
    summary = client.get("/api/v1/active-tasks/summary").json()
    assert summary["count"] == 1
    assert "do not consume ChatGPT" in summary["note"]
    runs = client.get(f"/api/v1/active-tasks/{task_id}/runs").json()
    assert runs["count"] == 0
    assert client.patch(f"/api/v1/active-tasks/{task_id}", json={"enabled": False}).json()["enabled"] is False


@pytest.mark.asyncio
async def test_foreman_dispatcher_builds_single_iteration_campaign(monkeypatch, tmp_path: Path):
    root = tmp_path / "ChatForeman"
    root.mkdir()
    (root / "foreman.py").write_text("# fake", encoding="utf-8")
    calls = []

    class Result:
        returncode = 0
        stdout = json.dumps({"id": "campaign-123", "status": "active"})
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr(active_tasks.subprocess, "run", fake_run)
    dispatcher = ForemanDispatcher(root=root, python_executable="python")
    task = active_tasks.ActiveTask(
        id="t1", project_id="ai-world", name="Universe iteration", preferred_runtime="chatgpt_web",
        created_at=to_iso(utc_now()), updated_at=to_iso(utc_now()),
    )
    receipt = await dispatcher.dispatch(task, "run-abc")
    assert receipt.ref_id == "campaign-123"
    args = calls[0][0]
    assert args[2:6] == ["iterate", "1", "ai-world", "--name"]
    assert "--runtime" in args
    assert "chatgpt_web" in args


def test_mcp_catalog_exposes_read_and_write_active_task_tools_correctly():
    from synapse_daemon.mcp_connector import _tool_specs
    read_names = {tool["name"] for tool in _tool_specs(False)}
    write_names = {tool["name"] for tool in _tool_specs(True)}
    assert "synapse_list_active_tasks" in read_names
    assert "synapse_create_active_task" not in read_names
    assert "synapse_update_active_task" not in read_names
    assert "synapse_create_active_task" in write_names
    assert "synapse_update_active_task" in write_names


def test_mcp_can_create_and_list_more_than_five_synapse_active_tasks(tmp_path: Path, monkeypatch):
    from synapse_daemon.app import build_app
    from synapse_daemon.ws import EventBus
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    db = Storage(tmp_path / "mcp-data")
    db.open()
    db.migrate()
    with db.transaction() as conn:
        projects.create(conn, Project(id="demo-project", name="Demo", path=str(tmp_path), launch_cmd="echo hi"))
    app = build_app(db, EventBus())
    token = app.state.auth.local_token
    client = TestClient(app)

    def rpc(name: str, arguments: dict):
        response = client.post(
            f"/mcp/{token}",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
        )
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert result["isError"] is False, result
        return json.loads(result["content"][0]["text"])

    for idx in range(7):
        created = rpc(
            "synapse_create_active_task",
            {"project_id": "demo-project", "name": f"Task {idx}", "interval_seconds": 3600},
        )
        assert created["project_id"] == "demo-project"
    listed = rpc("synapse_list_active_tasks", {"project_id": "demo-project"})
    assert listed["count"] == 7
    assert "do not consume ChatGPT" in listed["note"]
    db.close()
