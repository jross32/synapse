"""REST endpoints for interactive PTY sessions (v0.1.25 · ADR-0002 Phase A).

  GET    /api/v1/pty                       -- list active sessions
  POST   /api/v1/pty                       -- create a session
  GET    /api/v1/pty/{id}                  -- session summary + scrollback
  POST   /api/v1/pty/{id}/input            -- write bytes to the child
  POST   /api/v1/pty/{id}/resize           -- set the PTY window size
  DELETE /api/v1/pty/{id}                  -- close the session

Live output rides the WebSocket bus as ``v1.pty.session_output`` events
(see ``pty_sessions.py``); these REST endpoints handle the control plane.
"""

from __future__ import annotations

import base64
import shutil
import sys
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .errors import invalid, not_found
from .pty_sessions import PtySession, PtySessionManager


class SpawnRequest(BaseModel):
    argv: list[str] = Field(..., min_length=1)
    cwd: str | None = None
    env: dict[str, str] | None = None
    rows: int = Field(default=24, ge=1, le=300)
    cols: int = Field(default=80, ge=1, le=500)


class InputRequest(BaseModel):
    # The renderer base64-encodes to keep raw control bytes intact;
    # `text` is a convenience for tests + curl.
    data: str | None = None
    text: str | None = None


class ResizeRequest(BaseModel):
    rows: int = Field(..., ge=1, le=300)
    cols: int = Field(..., ge=1, le=500)


def _summary_dict(session: PtySession) -> dict[str, Any]:
    return session.summary().__dict__


def build_pty_router(manager: PtySessionManager) -> APIRouter:
    router = APIRouter(prefix="/pty", tags=["pty"])

    @router.get("/probe", response_model=None)
    async def probe(cmd: str) -> dict[str, Any]:
        """Cheap "is this binary on PATH?" check (v0.1.28).

        The Sessions page hits this before spawning so we can show an
        Install dialog instead of a raw "command not found" toast when
        the user clicks Claude / Codex / anything else that may not be
        installed yet.
        """

        resolved = shutil.which(cmd)
        return {"cmd": cmd, "available": resolved is not None, "resolved": resolved}

    @router.get("", response_model=None)
    async def list_sessions() -> dict[str, Any]:
        return {"sessions": [_summary_dict(s) for s in manager.list()]}

    @router.post("", response_model=None, status_code=201)
    async def spawn(payload: SpawnRequest) -> dict[str, Any]:
        try:
            session = await manager.spawn(
                argv=payload.argv,
                cwd=payload.cwd,
                env=payload.env,
                rows=payload.rows,
                cols=payload.cols,
            )
        except FileNotFoundError as exc:
            raise invalid("pty", str(exc))
        except ValueError as exc:
            raise invalid("pty", str(exc))
        return _summary_dict(session)

    @router.get("/{session_id}", response_model=None)
    async def get_one(session_id: str) -> dict[str, Any]:
        session = manager.get(session_id)
        if session is None:
            raise not_found("pty", session_id)
        return {
            **_summary_dict(session),
            "scrollback": base64.b64encode(session.scrollback_bytes()).decode("ascii"),
        }

    @router.post("/{session_id}/input", response_model=None)
    async def write_input(session_id: str, payload: InputRequest) -> dict[str, Any]:
        session = manager.get(session_id)
        if session is None:
            raise not_found("pty", session_id)
        if payload.data is None and payload.text is None:
            raise invalid("pty", "Provide 'data' (base64) or 'text'.")
        if payload.data is not None:
            try:
                buf = base64.b64decode(payload.data, validate=True)
            except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
                raise invalid("pty", f"'data' is not valid base64: {exc}")
        else:
            assert payload.text is not None
            buf = payload.text.encode("utf-8")
        await session.write(buf)
        return {"ok": True, "bytes": len(buf)}

    @router.post("/{session_id}/resize", response_model=None)
    async def resize(session_id: str, payload: ResizeRequest) -> dict[str, Any]:
        session = manager.get(session_id)
        if session is None:
            raise not_found("pty", session_id)
        await session.resize(payload.rows, payload.cols)
        return _summary_dict(session)

    @router.delete("/{session_id}", status_code=204, response_model=None)
    async def close_session(session_id: str) -> None:
        closed = await manager.close(session_id)
        if not closed:
            raise not_found("pty", session_id)

    return router
