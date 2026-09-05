"""ChatGPT compatibility shim for Synapse's remote MCP endpoint.

ChatGPT's MCP connector/runtime has periodically treated tool-only servers as
unavailable even when ``initialize`` and ``tools/list`` succeeded.  In August
2026, current connector reports showed the failure disappearing once the
server advertised the standard MCP ``resources`` capability and returned one
valid readable resource.

Synapse's core MCP router is intentionally hand-rolled and stateless.  This
small middleware keeps the compatibility behavior isolated: it only handles
``initialize``, ``resources/list`` and ``resources/read`` on ``/mcp/<token>``;
all tool calls and every other request continue to the existing router.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

DEFAULT_PROTOCOL_VERSION = "2025-06-18"
ABOUT_RESOURCE_URI = "synapse://connector/about"


def _ok(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }


class ChatGPTMcpCompatMiddleware(BaseHTTPMiddleware):
    """Advertise one readable MCP resource for ChatGPT connector compatibility.

    The middleware is deliberately narrow.  It never handles ``tools/list`` or
    ``tools/call`` and therefore cannot change Synapse's tool authorization,
    annotations, write gating, dispatch lanes, or audit behavior.
    """

    def __init__(self, app: Any, *, token: str, version: str) -> None:
        super().__init__(app)
        self._token = token
        self._version = version

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method != "POST" or not request.url.path.startswith("/mcp/"):
            return await call_next(request)

        try:
            payload = await request.json()
        except Exception:  # malformed/non-JSON requests belong to the core router
            return await call_next(request)
        if not isinstance(payload, dict):
            return await call_next(request)

        method = payload.get("method")
        if method not in {"initialize", "resources/list", "resources/read"}:
            return await call_next(request)

        message_id = payload.get("id")
        if not self._token or request.url.path != f"/mcp/{self._token}":
            return JSONResponse(
                _error(message_id, -32001, "Unauthorized"),
                status_code=401,
            )

        if method == "initialize":
            params = payload.get("params")
            requested = params.get("protocolVersion") if isinstance(params, dict) else None
            return JSONResponse(
                _ok(
                    message_id,
                    {
                        "protocolVersion": requested or DEFAULT_PROTOCOL_VERSION,
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {"subscribe": False, "listChanged": False},
                        },
                        "serverInfo": {"name": "synapse", "version": self._version},
                        "instructions": (
                            "Synapse connector. Call synapse_get_context first. "
                            "Use tools for project, runtime, file, browser, desktop, and "
                            "workflow operations. The about resource exists for MCP client "
                            "compatibility; it is not a substitute for Synapse tools."
                        ),
                    },
                )
            )

        if method == "resources/list":
            return JSONResponse(
                _ok(
                    message_id,
                    {
                        "resources": [
                            {
                                "uri": ABOUT_RESOURCE_URI,
                                "name": "synapse-connector-about",
                                "title": "Synapse connector information",
                                "description": (
                                    "Identifies this Synapse MCP server and its purpose."
                                ),
                                "mimeType": "text/plain",
                            }
                        ]
                    },
                )
            )

        params = payload.get("params")
        uri = params.get("uri") if isinstance(params, dict) else None
        if uri != ABOUT_RESOURCE_URI:
            return JSONResponse(
                _error(message_id, -32002, f"Resource not found: {uri!r}")
            )
        return JSONResponse(
            _ok(
                message_id,
                {
                    "contents": [
                        {
                            "uri": ABOUT_RESOURCE_URI,
                            "mimeType": "text/plain",
                            "text": (
                                f"Synapse daemon {self._version}. "
                                "AI-first local control plane for durable project state, "
                                "multi-AI coordination, tools, quality gates, and execution."
                            ),
                        }
                    ]
                },
            )
        )
