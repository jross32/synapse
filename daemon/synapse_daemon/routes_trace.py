"""Synapse Trace / Flight Recorder API routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from .storage import Storage
from .trace_recorder import analyze_events, ingest_runtime_sources, list_events, record_event


def build_trace_router(storage: Storage) -> APIRouter:
    router = APIRouter()

    @router.get("/trace/events", response_model=None)
    async def get_trace_events(
        limit: int = Query(default=120, ge=1, le=500),
        category: str | None = None,
        project_id: str | None = None,
        source: str | None = None,
        status: str | None = None,
        sync_runtime: bool = True,
    ):
        imported = ingest_runtime_sources(storage) if sync_runtime else {}
        return {
            "items": list_events(
                storage,
                limit=limit,
                category=category,
                project_id=project_id,
                source=source,
                status=status,
            ),
            "runtime_imported": imported,
        }

    @router.get("/trace/analysis", response_model=None)
    async def get_trace_analysis(
        window_hours: int = Query(default=24, ge=1, le=720),
        sync_runtime: bool = True,
    ):
        imported = ingest_runtime_sources(storage) if sync_runtime else {}
        return {
            **analyze_events(storage, window_hours=window_hours),
            "runtime_imported": imported,
        }

    @router.post("/trace/events", response_model=None, status_code=201)
    async def create_trace_event(payload: dict):
        event_id = record_event(
            storage,
            source=str(payload.get("source") or "operator"),
            category=str(payload.get("category") or "note"),
            action=str(payload.get("action") or "annotation"),
            status=str(payload.get("status") or "info"),
            severity=str(payload.get("severity") or payload.get("status") or "info"),
            summary=str(payload.get("summary") or ""),
            project_id=str(payload["project_id"]) if payload.get("project_id") else None,
            session_id=str(payload["session_id"]) if payload.get("session_id") else None,
            correlation_id=str(payload["correlation_id"]) if payload.get("correlation_id") else None,
            duration_ms=float(payload["duration_ms"]) if payload.get("duration_ms") is not None else None,
            error_code=str(payload["error_code"]) if payload.get("error_code") else None,
            details=payload.get("details") if isinstance(payload.get("details"), dict) else {},
        )
        return {"id": event_id, "recorded": True}

    return router
