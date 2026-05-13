"""Error envelope (Contract #4).

Every REST 4xx/5xx response and every WebSocket error event uses
``ErrorEnvelope``. UI has a single component that renders any failure.

This module is the canonical source for error shape — when ``scripts/gen-types.ps1``
runs, ``ErrorEnvelope`` is exported to TypeScript so the frontend cannot drift.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    """Single error shape used everywhere.

    Examples
    --------
    >>> e = ErrorEnvelope(code="project.not_found", message="Project 'x' missing")
    >>> e.retryable
    False
    >>> e.model_dump()["code"]
    'project.not_found'
    """

    code: str = Field(
        ...,
        description="Machine-readable error code, namespaced by entity (e.g. 'project.not_found').",
        examples=["project.not_found", "tunnel.cloudflared_missing", "ws.replay_window_exceeded"],
    )
    message: str = Field(
        ...,
        description="Human-readable explanation. UI renders this directly.",
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured payload (validation errors, stack hash, etc.).",
    )
    retryable: bool = Field(
        default=False,
        description="If true, UI may offer a 'Retry' button.",
    )


class SynapseError(Exception):
    """Base exception that carries an :class:`ErrorEnvelope`.

    Daemon code raises these; the FastAPI exception handler converts them to
    JSON responses. Never raise bare exceptions across the API boundary.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        status: int = 400,
    ) -> None:
        super().__init__(message)
        self.envelope = ErrorEnvelope(
            code=code, message=message, details=details, retryable=retryable
        )
        self.status = status


# Common helpers — extend as new error codes appear.
def not_found(entity: str, entity_id: str) -> SynapseError:
    return SynapseError(
        code=f"{entity}.not_found",
        message=f"{entity.capitalize()} '{entity_id}' was not found.",
        status=404,
    )


def conflict(entity: str, message: str, **details: Any) -> SynapseError:
    return SynapseError(
        code=f"{entity}.conflict",
        message=message,
        details=details or None,
        status=409,
    )


def invalid(entity: str, message: str, **details: Any) -> SynapseError:
    return SynapseError(
        code=f"{entity}.invalid",
        message=message,
        details=details or None,
        status=422,
    )
