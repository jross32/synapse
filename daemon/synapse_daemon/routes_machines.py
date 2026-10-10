"""REST surface for installed Synapse host machines."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import AuthManager, require_token
from .machine_fleet import list_machines, upsert_local_machine
from .storage import Storage


class RenameMachineRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


def build_machine_router(storage: Storage, auth: AuthManager, data_dir, version: str | None = None) -> APIRouter:
    router=APIRouter(tags=["machines"])
    guard=Depends(require_token(auth))

    @router.get("/machines", dependencies=[guard])
    async def machines() -> dict:
        return {"machines": list_machines(storage)}

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
