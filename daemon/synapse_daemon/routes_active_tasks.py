"""REST API for Synapse-owned Active Tasks."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from . import active_tasks as tasks
from . import projects as projects_module
from .active_tasks import ActiveTaskCreate, ActiveTaskScheduler, ActiveTaskUpdate
from .ai_context_memory import append_capture_note
from .audit import AuditRecord, audit
from .errors import not_found
from .storage import Storage


def _get_task_or_404(storage: Storage, task_id: str):
    try:
        return tasks.get_task(storage.conn, task_id)
    except KeyError:
        raise not_found("active_task", task_id)


def build_active_tasks_router(storage: Storage, scheduler: ActiveTaskScheduler) -> APIRouter:
    router = APIRouter(tags=["active-tasks"])

    @router.get("/active-tasks", response_model=None)
    async def list_active_tasks(
        project_id: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        rows = tasks.list_tasks(storage.conn, project_id=project_id, enabled=enabled)
        return {"tasks": [row.model_dump(mode="json") for row in rows], "count": len(rows)}

    @router.get("/active-tasks/summary", response_model=None)
    async def active_tasks_summary() -> dict[str, Any]:
        rows = tasks.list_tasks(storage.conn)
        return {
            "count": len(rows),
            "enabled": sum(1 for row in rows if row.enabled),
            "disabled": sum(1 for row in rows if not row.enabled),
            "due": sum(1 for row in tasks.due_tasks(storage.conn)),
            "running_or_dispatched": sum(1 for row in rows if row.last_status in {"running", "dispatched"}),
            "note": "Synapse Active Tasks are stored and scheduled by Synapse and do not consume ChatGPT built-in task slots.",
        }

    @router.post("/active-tasks", response_model=None, status_code=201)
    async def create_active_task(payload: ActiveTaskCreate) -> dict[str, Any]:
        project = projects_module.get(storage.conn, payload.project_id)
        with storage.transaction() as conn:
            row = tasks.create_task(conn, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="active_task",
                    entity_id=row.id,
                    action="create",
                    source=payload.source,
                    result="success",
                    details={
                        "project_id": row.project_id,
                        "schedule_kind": row.schedule_kind.value,
                        "interval_seconds": row.interval_seconds,
                        "preferred_runtime": row.preferred_runtime,
                    },
                ),
            )
        append_capture_note(
            data_dir=storage.data_dir,
            project_id=project.id,
            project_name=project.name,
            source="active-task",
            note=(
                f"Synapse Active Task enabled: **{row.name}** ({row.id}).\n\n"
                f"Recurring directive: {row.prompt or 'Continue the project according to its current AI context and highest-value verified next step.'}\n\n"
                f"Runtime preference: `{row.preferred_runtime}`; cadence: `{row.schedule_kind.value}`"
                + (f" every {row.interval_seconds} seconds" if row.interval_seconds else "")
                + ". This task is scheduled by Synapse itself, not ChatGPT built-in Tasks."
            ),
        )
        return row.model_dump(mode="json")

    @router.get("/active-tasks/{task_id}", response_model=None)
    async def get_active_task(task_id: str) -> dict[str, Any]:
        return _get_task_or_404(storage, task_id).model_dump(mode="json")

    @router.patch("/active-tasks/{task_id}", response_model=None)
    async def patch_active_task(task_id: str, payload: ActiveTaskUpdate) -> dict[str, Any]:
        _get_task_or_404(storage, task_id)
        with storage.transaction() as conn:
            row = tasks.update_task(conn, task_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="active_task",
                    entity_id=row.id,
                    action="update",
                    source=payload.source,
                    result="success",
                    details={"project_id": row.project_id, "enabled": row.enabled, "next_run_at": row.next_run_at},
                ),
            )
        if payload.prompt is not None:
            project = projects_module.get(storage.conn, row.project_id)
            append_capture_note(
                data_dir=storage.data_dir,
                project_id=project.id,
                project_name=project.name,
                source="active-task",
                note=f"Synapse Active Task **{row.name}** ({row.id}) directive updated:\n\n{row.prompt}",
            )
        return row.model_dump(mode="json")

    @router.delete("/active-tasks/{task_id}", status_code=204, response_model=None)
    async def remove_active_task(task_id: str) -> None:
        row = _get_task_or_404(storage, task_id)
        with storage.transaction() as conn:
            tasks.delete_task(conn, task_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="active_task", entity_id=task_id, action="delete",
                    source=row.source, result="success", details={"project_id": row.project_id},
                ),
            )

    @router.post("/active-tasks/{task_id}/run-now", response_model=None)
    async def run_active_task_now(task_id: str) -> dict[str, Any]:
        row = _get_task_or_404(storage, task_id)
        run = await scheduler.run_now(task_id)
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="active_task_run", entity_id=run.id, action="run_now",
                    source=row.source, result="success" if run.status.value == "dispatched" else run.status.value,
                    details={"project_id": row.project_id, "task_id": row.id, "dispatch_ref": run.dispatch_ref},
                ),
            )
        return run.model_dump(mode="json")

    @router.get("/active-tasks/{task_id}/runs", response_model=None)
    async def active_task_runs(task_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        _get_task_or_404(storage, task_id)
        rows = tasks.list_runs(storage.conn, task_id, limit=limit)
        return {"runs": [row.model_dump(mode="json") for row in rows], "count": len(rows)}

    return router
