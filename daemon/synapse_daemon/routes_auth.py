"""REST routes for device auth + pairing (Milestone H · v0.1.11).

  GET    /api/v1/auth/local-token
         -> the daemon's local token. Trusted-local callers only (the desktop
            app + the dev browser) — a tunnelled request is refused. This is
            how the desktop bootstraps its credential.

  POST   /api/v1/pair/code
         -> mint a fresh 6-digit pairing code. Authed (desktop-only in
            practice — a phone has no token yet).

  POST   /api/v1/pair
         -> redeem a pairing code; returns a device token. OPEN — the phone
            being paired has no token yet.

  GET    /api/v1/pair/devices            -> list paired devices. Authed.
  DELETE /api/v1/pair/devices/{id}       -> revoke a device. Authed.

All under ``/api/v1`` — mounted by :func:`synapse_daemon.app.build_app`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .audit import AuditRecord, audit
from .auth import AuthManager, is_trusted_local, require_token
from .errors import SynapseError
from .models import AuditSource
from .storage import Storage


class PairRequest(BaseModel):
    """Body for ``POST /pair`` — the code shown on the desktop + a label."""

    code: str = Field(..., min_length=1)
    device_name: str = ""


def build_auth_router(storage: Storage, auth: AuthManager) -> APIRouter:
    router = APIRouter(tags=["auth"])
    guard = Depends(require_token(auth))

    @router.get("/auth/local-token", response_model=None)
    async def local_token(request: Request) -> dict:
        if not is_trusted_local(request):
            raise SynapseError(
                code="auth.forbidden",
                message="The local token is only available to this machine.",
                status=403,
            )
        return {"token": auth.local_token}

    @router.post("/pair/code", response_model=None, dependencies=[guard])
    async def new_pairing_code() -> dict:
        return auth.issue_code()

    @router.post("/pair", response_model=None)
    async def redeem_pairing_code(payload: PairRequest) -> dict:
        result = auth.redeem(payload.code, payload.device_name)
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="device",
                    entity_id=result["device"]["id"],
                    action="pair",
                    source=AuditSource.MOBILE,
                    result="success",
                    details={"name": result["device"]["name"]},
                ),
            )
        return result

    @router.get("/pair/devices", response_model=None, dependencies=[guard])
    async def list_devices() -> dict:
        return {"devices": auth.list_devices()}

    @router.delete("/pair/devices/{device_id}", status_code=204, dependencies=[guard])
    async def revoke_device(device_id: str) -> None:
        auth.revoke(device_id)
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="device",
                    entity_id=device_id,
                    action="revoke",
                    source=AuditSource.DESKTOP,
                    result="success",
                ),
            )

    return router
