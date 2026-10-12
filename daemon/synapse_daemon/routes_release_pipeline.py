"""Authenticated local release orchestration, discoverable by native Synapse agents."""
from __future__ import annotations

import os
import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .audit import AuditRecord, audit
from .errors import SynapseError, invalid, not_found
from .release_pipeline import ReleasePipeline
from .storage import Storage
from .synapse_dev import SynapseDevManager


class ReleaseRequest(BaseModel):
    version: str
    source_root: str | None = None
    publish_requested: bool = False
    instruction: str = Field(default="", max_length=4000)


class PublisherConfigRequest(BaseModel):
    source_root: str
    site_root: str


class ReleaseProofRequest(BaseModel):
    evidence_path: str


def build_release_pipeline_router(storage: Storage, developer: SynapseDevManager) -> APIRouter:
    manager = ReleasePipeline(storage.data_dir, developer.repo_root)
    async def bind_events(request: Request) -> None:
        loop = asyncio.get_running_loop()
        bus = request.app.state.bus
        manager.on_change = lambda payload: asyncio.run_coroutine_threadsafe(bus.publish("v1.release.changed", payload), loop)
    router = APIRouter(prefix="/release-pipeline", tags=["release-pipeline"], dependencies=[Depends(bind_events)])

    def owner(request: Request) -> None:
        subject = getattr(request.state, "auth_subject", None)
        if subject is None or subject.kind != "local":
            raise SynapseError("release_pipeline.owner_required", "Release mutations require the local owner controller; scoped workers can read the plan.", status=403)

    def enabled() -> None:
        if not developer.enabled():
            raise SynapseError("release_pipeline.disabled", "Enable Synapse developer actions before building or publishing source releases.", status=403)

    def record(run_id: str, action: str) -> None:
        with storage.transaction() as conn:
            audit(conn, AuditRecord(entity_type="release_run", entity_id=run_id, action=action, details={"pipeline": "synapse-native", "private_key_logged": False}))

    def invoke(method, run_id: str, *args):  # noqa: ANN001
        try:
            return method(run_id, *args)
        except KeyError:
            raise not_found("release_run", run_id)
        except ValueError as error:
            raise invalid("release_run", str(error))

    @router.get("", response_model=None)
    def list_release_requests() -> dict[str, Any]:
        return {"runs": manager.list(), "required_order": ["request", "plan", "start", "proof", "request-publication", "publish", "verify-live"], "developer_enabled": developer.enabled(), "publisher": manager.publisher_configuration(), "execution": "local daemon background worker, independent of ChatGPT Work Mode", "publish_requires_explicit_request": True}

    @router.post("", status_code=201, response_model=None, dependencies=[Depends(owner)])
    def create_release_request(payload: ReleaseRequest) -> dict[str, Any]:
        try:
            row = manager.request(payload.version, payload.source_root, payload.publish_requested, payload.instruction)
        except ValueError as error:
            raise invalid("release_run", str(error))
        record(row["id"], "release.request")
        return row

    @router.put("/publisher", response_model=None, dependencies=[Depends(owner)])
    def configure_release_publisher(payload: PublisherConfigRequest) -> dict[str, Any]:
        enabled()
        try:
            configuration = manager.configure_publisher(payload.source_root, payload.site_root)
        except ValueError as error:
            raise invalid("release_publisher", str(error))
        record("publisher", "release.publisher_configuration")
        return configuration

    @router.get("/{run_id}", response_model=None)
    def get_release_run(run_id: str) -> dict[str, Any]:
        return invoke(manager.get, run_id)

    @router.get("/{run_id}/plan", response_model=None)
    def get_release_plan(run_id: str) -> dict[str, Any]:
        return {"steps": invoke(manager.plan, run_id), "executes_on_start": True, "publication_is_separate": True}

    @router.post("/{run_id}/start", response_model=None, dependencies=[Depends(owner)])
    def start_release_run(run_id: str) -> dict[str, Any]:
        enabled()
        row = invoke(manager.start, run_id)
        record(run_id, "release.start")
        return row

    @router.post("/{run_id}/resume", response_model=None, dependencies=[Depends(owner)])
    def resume_release_run(run_id: str) -> dict[str, Any]:
        enabled()
        row = invoke(manager.resume, run_id)
        record(run_id, "release.resume")
        return row

    @router.post("/{run_id}/proof", response_model=None, dependencies=[Depends(owner)])
    def attach_release_proof(run_id: str, payload: ReleaseProofRequest) -> dict[str, Any]:
        row = invoke(manager.attach_proof, run_id, payload.evidence_path)
        record(run_id, "release.proof")
        return row

    @router.post("/{run_id}/request-publication", response_model=None, dependencies=[Depends(owner)])
    def request_release_publication(run_id: str) -> dict[str, Any]:
        enabled()
        row = invoke(manager.request_publication, run_id)
        record(run_id, "release.publication_requested")
        return row

    @router.post("/{run_id}/publish", response_model=None, dependencies=[Depends(owner)])
    def publish_release_run(run_id: str) -> dict[str, Any]:
        enabled()
        row = invoke(manager.publish, run_id)
        record(run_id, "release.publish")
        return row

    @router.post("/{run_id}/verify-live", response_model=None, dependencies=[Depends(owner)])
    def verify_release_live(run_id: str) -> dict[str, Any]:
        enabled()
        row = invoke(manager.verify_live, run_id)
        record(run_id, "release.live_verification")
        return row

    return router
