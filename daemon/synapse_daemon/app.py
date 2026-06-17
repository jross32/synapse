"""FastAPI app factory (Contracts #4, #5, #7, #11, #15).

For Milestone B this app exposes:

  • ``GET  /api/v1/health``  — daemon liveness, version, applied schema,
                                contracts honoured (Contract #7).
  • ``WS   /api/v1/ws``     — the event bus hub (Contract #5).

The factory pattern (``build_app(storage, bus)``) lets tests instantiate the
app against a temp directory without going through ``__main__``.

Every uncaught :class:`SynapseError` from a handler is rendered as an
:class:`ErrorEnvelope` JSON response (Contract #4). CORS is opened just wide
enough for the Electron renderer's Vite dev server and the loopback origin
(Contract #15 — no third-party calls).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api_versions import API_PREFIX, event_name
from .auth import AuthManager, ensure_local_token, require_token
from .errors import ErrorEnvelope, SynapseError
from .models import HealthResponse
from .orphan_reconciler import ReconcileOutcome, summarise
from .process_manager import ProcessManager
from .pty_sessions import PtySessionManager
from .routes_ai import build_ai_router
from .routes_audit import build_audit_router
from .routes_files import build_files_router
from .routes_imports import build_imports_router
from .routes_marketplace import build_marketplace_router
from .routes_quick_actions import build_quick_actions_router
from .routes_system import build_system_router
from .routes_pty import build_pty_router
from .routes_workbench import build_workbench_router
from .routes_auth import build_auth_router
from .routes_discovery import build_discovery_router
from .routes_projects import build_projects_router
from .routes_snapshot import build_snapshot_router
from .routes_tools import build_tools_router
from .storage import Storage
from .time_utils import to_iso, utc_now
from .tools_registry import ToolRegistry
from .ws import EventBus, WsHub

log = logging.getLogger(__name__)


# CORS origins permitted to talk to the daemon. The packaged Electron build
# loads from a ``file://`` origin which JSON serialises as ``null`` — so we
# allow ``null`` explicitly. The Vite dev server is 5173.
_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "null",
]


def build_app(
    storage: Storage,
    bus: EventBus,
    *,
    process_manager: ProcessManager | None = None,
    tool_registry: ToolRegistry | None = None,
    auth: AuthManager | None = None,
) -> FastAPI:
    """Construct the FastAPI app bound to a Storage + EventBus.

    ``process_manager``, ``tool_registry`` and ``auth`` are created on demand
    if not supplied (so tests that only care about ``/health`` don't have to
    wire them up themselves). A freshly-created registry is loaded immediately
    — scanning ``tools/`` is pure file IO and safe before the lifespan starts.
    """

    started_at = utc_now()
    if process_manager is None:
        process_manager = ProcessManager(storage, bus)
    if tool_registry is None:
        tool_registry = ToolRegistry(Path("tools"), bus, storage)
        tool_registry.load()
    if auth is None:
        auth = AuthManager(storage, ensure_local_token(storage.data_dir))

    app = FastAPI(
        title="Synapse daemon",
        version=__version__,
        docs_url=None,         # /docs deferred until Milestone H mobile UI
        redoc_url=None,
        openapi_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "X-Synapse-Token"],
    )

    # ── exception handler ───────────────────────────────────────────────

    @app.exception_handler(SynapseError)
    async def synapse_error_handler(request: Request, exc: SynapseError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.envelope.model_dump())

    @app.exception_handler(Exception)
    async def fallback_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        envelope = ErrorEnvelope(
            code="server.internal",
            message="An unexpected error occurred. See daemon logs for details.",
            retryable=False,
        )
        return JSONResponse(status_code=500, content=envelope.model_dump())

    # ── routes ──────────────────────────────────────────────────────────

    @app.get(f"{API_PREFIX}/health")
    async def health() -> HealthResponse:
        return HealthResponse(ok=True, version=__version__, started_at=started_at)

    hub = WsHub(bus, auth)

    @app.websocket(f"{API_PREFIX}/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await hub.handle(websocket)

    # Every data router requires a valid X-Synapse-Token (Milestone H).
    token_guard = Depends(require_token(auth))

    # Mount the REST routers under /api/v1.
    app.include_router(
        build_projects_router(storage, process_manager),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )
    app.include_router(
        build_discovery_router(storage), prefix=API_PREFIX, dependencies=[token_guard]
    )
    app.include_router(
        build_tools_router(storage, tool_registry),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )
    app.include_router(
        build_snapshot_router(storage, tool_registry),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )
    app.include_router(
        build_audit_router(storage), prefix=API_PREFIX, dependencies=[token_guard]
    )
    app.include_router(
        build_marketplace_router(tool_registry),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )

    # ── PTY sessions (v0.1.25 · ADR-0002 Phase A) ──────────────────────
    # The manager is attached to the bus so the pty.spawn tool primitive
    # can find it without an import cycle. Storage is passed in so
    # workbench-tagged sessions can persist their scrollback as a
    # transcript file on exit (ADR-0003 Phase D).
    pty_manager = PtySessionManager(bus, storage=storage)
    bus._pty_manager = pty_manager  # type: ignore[attr-defined]
    app.state.pty_manager = pty_manager
    app.include_router(
        build_pty_router(pty_manager),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )
    # Phase B workbench (v0.1.29): "Open in workbench" on an Apps tile.
    app.include_router(
        build_workbench_router(storage, pty_manager),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )
    # ADR-0003 Phase A files (v0.1.30): per-project + shared uploads.
    app.include_router(
        build_files_router(storage),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )
    # ADR-0003 Phase E (v0.1.33): ChatGPT export.zip import.
    app.include_router(
        build_imports_router(storage),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )
    # ADR-0003 Phase F (v0.1.34): AI quick-action templates.
    app.include_router(
        build_quick_actions_router(storage, pty_manager),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )
    # System network controls (v0.1.35): LAN exposure toggle.
    app.include_router(
        build_system_router(storage, storage.data_dir),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )
    # AI-facing digest -- what a Claude session in a tab should read first.
    app.include_router(
        build_ai_router(storage, tool_registry, pty_manager),
        prefix=API_PREFIX,
        dependencies=[token_guard],
    )
    # The auth router guards its own routes (some are open: /pair, /local-token).
    app.include_router(build_auth_router(storage, auth), prefix=API_PREFIX)

    # Serve the mobile Web UI (Milestone H). Static files are open — a phone
    # must load the page before it can pair. Mounted only if the folder ships.
    # Resolve from the package location so the path holds no matter the CWD.
    mobile_dir = Path(__file__).resolve().parent.parent.parent / "mobile"
    if (mobile_dir / "index.html").exists():
        app.mount(
            "/mobile",
            StaticFiles(directory=mobile_dir, html=True),
            name="mobile",
        )

    # Stash state on the app for tests + later wiring.
    app.state.storage = storage
    app.state.bus = bus
    app.state.process_manager = process_manager
    app.state.tool_registry = tool_registry
    app.state.auth = auth
    app.state.started_at = started_at

    return app


async def boot_publish_daemon_started(bus: EventBus, schema_migration: int) -> None:
    """Announce the daemon's arrival on the event bus.

    Called by ``__main__`` after migrations and reconciliation finish, so the
    very first event subscribers see is a clean state checkpoint.
    """

    await bus.publish(
        event_name("daemon", "started"),
        {
            "version": __version__,
            "schema_migration": schema_migration,
            "started_at": to_iso(utc_now()),
            "contracts": list(range(1, 29)),
        },
    )


async def boot_publish_reconciliation(
    bus: EventBus,
    outcomes: list,
) -> None:
    """Emit one event per non-trivial reconcile outcome.

    Re-attached rows are quiet — the consumer was already tracking them in a
    previous life. We only broadcast the rows whose state actually changed.
    """

    report = summarise(outcomes)
    if report.inspected == 0:
        return

    for row in outcomes:
        if row.outcome == ReconcileOutcome.RE_ATTACHED:
            continue
        await bus.publish(
            event_name("process", "reconciled"),
            {
                "process_id": row.process_id,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "pid": row.pid,
                "outcome": row.outcome.value,
            },
        )

    await bus.publish(
        event_name("daemon", "reconciliation_complete"),
        report.model_dump(),
    )
