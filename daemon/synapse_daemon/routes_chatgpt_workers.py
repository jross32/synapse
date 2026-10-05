"""REST surface for durable ChatGPT UI worker conversations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from . import chatgpt_child_agents
from . import chatgpt_worker_chats as workers
from .audit import AuditRecord, audit
from .storage import Storage


class WorkerArchiveRequest(BaseModel):
    reason: str = Field(default="", max_length=1000)


class ProjectHomeReconcileRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="Foreman project-home reconciliation", max_length=1000)


def build_chatgpt_workers_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/chatgpt-workers", tags=["chatgpt-workers"])

    @router.get("/readiness", response_model=None)
    async def worker_readiness() -> dict[str, Any]:
        return chatgpt_child_agents.readiness(storage.data_dir)

    @router.post("/setup-browser", response_model=None)
    async def open_worker_setup_browser() -> dict[str, Any]:
        return chatgpt_child_agents.launch_setup_browser(storage.data_dir)

    @router.get("", response_model=None)
    async def list_worker_chats(
        project_id: str | None = Query(default=None),
        include_archived: bool = Query(default=False),
    ) -> dict[str, Any]:
        return {
            "project_name": workers.WORKER_PROJECT_NAME,
            "workers": [
                item.model_dump(mode="json")
                for item in workers.list_chats(
                    storage.conn,
                    project_id=project_id,
                    include_archived=include_archived,
                )
            ],
        }

    @router.get("/project-home/status", response_model=None)
    async def project_home_status(project_id: str = Query(min_length=1)) -> dict[str, Any]:
        return workers.project_home_report(storage.conn, project_id.strip())

    @router.post("/project-home/reconcile", response_model=None)
    async def project_home_reconcile(payload: ProjectHomeReconcileRequest) -> dict[str, Any]:
        with storage.transaction() as conn:
            result = workers.reconcile_project_home(
                conn,
                payload.project_id.strip(),
                reason=payload.reason,
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="chatgpt_worker_project_home",
                    entity_id=payload.project_id.strip(),
                    action="reconcile",
                    details={
                        "archived_worker_count": result["archived_worker_count"],
                        "provider_cleanup_count": len(result["provider_cleanup_urls"]),
                    },
                ),
            )
        return result

    @router.get("/{worker_chat_id}", response_model=workers.ChatGPTWorkerChat)
    async def get_worker_chat(worker_chat_id: str) -> workers.ChatGPTWorkerChat:
        return workers.get_chat(storage.conn, worker_chat_id)

    @router.post("/{worker_chat_id}/archive", response_model=workers.ChatGPTWorkerChat)
    async def archive_worker_chat(
        worker_chat_id: str, payload: WorkerArchiveRequest
    ) -> workers.ChatGPTWorkerChat:
        with storage.transaction() as conn:
            item = workers.archive_chat(conn, worker_chat_id, reason=payload.reason)
            audit(
                conn,
                AuditRecord(
                    entity_type="chatgpt_worker_chat",
                    entity_id=worker_chat_id,
                    action="archive",
                    details={"reason": payload.reason},
                ),
            )
        return item

    @router.post("/{worker_chat_id}/unarchive", response_model=workers.ChatGPTWorkerChat)
    async def unarchive_worker_chat(worker_chat_id: str) -> workers.ChatGPTWorkerChat:
        with storage.transaction() as conn:
            item = workers.unarchive_chat(conn, worker_chat_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="chatgpt_worker_chat",
                    entity_id=worker_chat_id,
                    action="unarchive",
                ),
            )
        return item

    return router
