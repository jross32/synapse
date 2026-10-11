"""REST surface for installed Synapse host machines."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import AuthManager, require_token
from .machine_fleet import list_machines, upsert_local_machine
from .mesh_inventory import hardware_inventory
from .mesh_transfer import preview_project_copy, copy_project
from . import projects as project_registry
from .storage import Storage


class CopyProjectRequest(BaseModel):
    folder_name: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    confirmed: bool = False


class RenameMachineRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


def build_machine_router(storage: Storage, auth: AuthManager, data_dir, version: str | None = None) -> APIRouter:
    router=APIRouter(tags=["machines"])
    guard=Depends(require_token(auth))

    @router.get("/machines", dependencies=[guard])
    async def machines() -> dict:
        return {"machines": list_machines(storage)}

    @router.get("/machines/local/inventory", dependencies=[guard])
    async def local_inventory() -> dict:
        # No credentials, serial numbers or user files leave the machine.
        return {"inventory": await asyncio.to_thread(hardware_inventory)}

    def require_local_owner(request: Request) -> None:
        if request.state.auth_subject.kind != "local":
            raise HTTPException(status_code=403, detail="Project copies require local owner authorization")

    @router.get("/machines/local/projects/{project_id}/copy-preview", dependencies=[guard])
    async def copy_preview(project_id: str, request: Request) -> dict:
        require_local_owner(request)
        item = project_registry.get_or_none(storage.conn, project_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Project not registered")
        try:
            return {"project_id": project_id, "preview": await asyncio.to_thread(
                preview_project_copy, Path(item.path)), "read_only": True}
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/machines/local/projects/{project_id}/copy", dependencies=[guard])
    async def copy_project_local(project_id: str, payload: CopyProjectRequest, request: Request) -> dict:
        require_local_owner(request)
        if not payload.confirmed:
            raise HTTPException(status_code=409, detail="Explicit confirmation required")
        item = project_registry.get_or_none(storage.conn, project_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Project not registered")
        base = Path.home() / "Synapse Imports"
        base.mkdir(parents=True, exist_ok=True)
        destination = base / payload.folder_name
        try:
            return {"project_id": project_id, "copy": await asyncio.to_thread(
                copy_project, Path(item.path), destination, Path.home())}
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/machines/local/heartbeat", dependencies=[guard])
    async def heartbeat() -> dict:
        return {"machine": upsert_local_machine(storage, data_dir, version)}

    @router.patch("/machines/{machine_id}", dependencies=[guard])
    async def rename(machine_id: str, payload: RenameMachineRequest) -> dict:
        with storage.transaction() as conn:
            cur=conn.execute(
                "UPDATE synapse_machines SET name=? WHERE id=? AND revoked=0",
                (payload.name.strip(), machine_id),
            )
            if cur.rowcount != 1:
                from .errors import SynapseError
                raise SynapseError(code="machine.not_found",message="Machine not found.",status=404)
        machine=next(m for m in list_machines(storage) if m["id"]==machine_id)
        return {"machine": machine}

    return router
