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

import socket

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .audit import AuditRecord, audit
from .auth import AuthManager, is_trusted_local, require_token
from .api_versions import event_name
from .errors import SynapseError
from .models import AuditSource
from .storage import Storage


class PairRequest(BaseModel):
    """Body for ``POST /pair`` — the code shown on the desktop + a label."""

    code: str = Field(..., min_length=1)
    device_name: str = ""


class PairClaimRequest(BaseModel):
    claim: str = Field(..., min_length=1)


class PairHandoffRequest(BaseModel):
    device_id: str | None = None


class PairedDeviceResponse(BaseModel):
    id: str
    name: str
    created_at: str
    last_seen_at: str | None = None


class PairingCodeResponse(BaseModel):
    code: str
    expires_at: str


class PairResponse(BaseModel):
    token: str
    device: PairedDeviceResponse
    computer_name: str


class PairClaimResponse(BaseModel):
    claim: str
    claim_id: str
    expires_at: str
    device: PairedDeviceResponse
    computer_name: str


class PairedDeviceListResponse(BaseModel):
    devices: list[PairedDeviceResponse]


def _computer_name() -> str:
    return socket.gethostname() or "This computer"


async def _publish_remote_access_updated(request: Request, reason: str) -> None:
    await request.app.state.bus.publish(
        event_name("remote_access", "updated"),
        {"reason": reason},
    )


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

    @router.post("/pair/code", response_model=PairingCodeResponse, dependencies=[guard])
    async def new_pairing_code(request: Request) -> PairingCodeResponse:
        result = auth.issue_code()
        await _publish_remote_access_updated(request, "pairing-code-issued")
        return PairingCodeResponse.model_validate(result)

    @router.post("/pair", response_model=PairResponse)
    async def redeem_pairing_code(payload: PairRequest, request: Request) -> PairResponse:
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
        await request.app.state.bus.publish(
            event_name("device", "paired"),
            {
                "device_id": result["device"]["id"],
                "device_name": result["device"]["name"],
            },
        )
        await _publish_remote_access_updated(request, "device-paired")
        return PairResponse(
            token=result["token"],
            device=PairedDeviceResponse.model_validate(result["device"]),
            computer_name=_computer_name(),
        )

    @router.post("/pair/handoff", response_model=PairClaimResponse, dependencies=[guard])
    async def create_handoff_claim(
        payload: PairHandoffRequest,
        request: Request,
    ) -> PairClaimResponse:
        token = request.headers.get("x-synapse-token")
        subject = auth.subject_for_token(token)
        if subject is None:
            raise SynapseError(
                code="auth.unauthorized",
                message="A valid X-Synapse-Token is required.",
                status=401,
            )

        target_device_id = payload.device_id or subject.device_id
        if not target_device_id:
            raise SynapseError(
                code="device.required",
                message="Choose which paired device should reconnect.",
                status=422,
            )
        if subject.kind != "local" and payload.device_id and payload.device_id != subject.device_id:
            raise SynapseError(
                code="device.forbidden",
                message="A paired device can only mint reconnect links for itself.",
                status=403,
            )

        result = auth.issue_claim(target_device_id)
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="device",
                    entity_id=target_device_id,
                    action="handoff",
                    source=AuditSource.MOBILE if subject.kind == "device" else AuditSource.DESKTOP,
                    result="success",
                    details={"claim_id": result["claim_id"]},
                ),
            )
        return PairClaimResponse(
            claim=result["claim"],
            claim_id=result["claim_id"],
            expires_at=result["expires_at"],
            device=PairedDeviceResponse.model_validate(result["device"]),
            computer_name=_computer_name(),
        )

    @router.post("/pair/claim", response_model=PairResponse)
    async def redeem_handoff_claim(
        payload: PairClaimRequest,
        request: Request,
    ) -> PairResponse:
        result = auth.redeem_claim(payload.claim)
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="device",
                    entity_id=result["device"]["id"],
                    action="reconnect",
                    source=AuditSource.MOBILE,
                    result="success",
                    details={"name": result["device"]["name"]},
                ),
            )
        await request.app.state.bus.publish(
            event_name("device", "reconnected"),
            {
                "device_id": result["device"]["id"],
                "device_name": result["device"]["name"],
            },
        )
        await _publish_remote_access_updated(request, "device-reconnected")
        return PairResponse(
            token=result["token"],
            device=PairedDeviceResponse.model_validate(result["device"]),
            computer_name=_computer_name(),
        )

    @router.get("/pair/devices", response_model=PairedDeviceListResponse, dependencies=[guard])
    async def list_devices() -> PairedDeviceListResponse:
        return PairedDeviceListResponse(
            devices=[PairedDeviceResponse.model_validate(device) for device in auth.list_devices()]
        )

    @router.delete("/pair/devices/{device_id}", status_code=204, dependencies=[guard])
    async def revoke_device(device_id: str, request: Request) -> None:
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
        await request.app.state.bus.publish(
            event_name("device", "revoked"),
            {"device_id": device_id},
        )
        await _publish_remote_access_updated(request, "device-revoked")

    return router
