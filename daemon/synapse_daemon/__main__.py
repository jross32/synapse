"""Entry point: ``python -m synapse_daemon`` (or the ``synapsed`` script).

Boot sequence:

  1. Parse args.
  2. Refuse Administrator unless ``--allow-admin`` (Contract #16).
  3. Open Storage at ``--data-dir``, apply pending migrations (Contract #9).
  4. Run orphan reconciliation against ``managed_processes`` (Contract #6).
  5. Build the FastAPI app with a lifespan that announces ``daemon.started`` +
     one event per reconciled row.
  6. Hand off to uvicorn on ``--host``:``--port`` (Contract #7).

After step 6 the daemon is live; the CLI / Electron renderer can connect to
``http://<host>:<port>/api/v1/health`` and ``ws://<host>:<port>/api/v1/ws``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from . import __version__, boot_config
from .app import boot_publish_daemon_started, boot_publish_reconciliation, build_app
from .auth import AuthManager, ensure_local_token
from .orphan_reconciler import reconcile, reconcile_project_statuses
from .process_manager import ProcessManager
from .security import assert_not_admin
from .seed import seed_default_projects
from .storage import Storage
from .tools_registry import ToolRegistry
from .ws import EventBus

log = logging.getLogger("synapse")

# Contract: daemon port is 7878 and only 7878. See AGENTS.md.
DEFAULT_PORT = 7878
DEFAULT_HOST = "127.0.0.1"          # loopback by default
LAN_HOST = "0.0.0.0"                # opt-in via --bind-lan
DEFAULT_DATA_DIR = Path("data")
DEFAULT_TOOLS_DIR = Path("tools")   # plugin manifests live here


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="synapsed",
        description="Synapse execution-layer daemon. Owns all managed processes.",
    )
    p.add_argument("--version", action="version", version=f"synapse-daemon {__version__}")
    p.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Interface to bind. Default: 127.0.0.1 (loopback only). "
             "Use --bind-lan to allow LAN access for the mobile UI.",
    )
    p.add_argument(
        "--bind-lan",
        action="store_true",
        help="Bind 0.0.0.0 instead of loopback so phones on the same Wi-Fi can reach the daemon.",
    )
    p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"TCP port. Default: {DEFAULT_PORT}.",
    )
    p.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Folder for the SQLite DB, logs, and per-tool data. Created if missing.",
    )
    p.add_argument(
        "--tools-dir",
        type=Path,
        default=DEFAULT_TOOLS_DIR,
        help="Folder of tool plugin manifests (tools/<id>/manifest.json). "
             f"Default: {DEFAULT_TOOLS_DIR}.",
    )
    p.add_argument(
        "--allow-admin",
        action="store_true",
        help="Permit running with Administrator/root privileges (default refuses — Contract #16).",
    )
    p.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging verbosity for the daemon (uvicorn inherits this).",
    )
    return p


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_lifespan(
    storage: Storage,
    bus: EventBus,
    pm: ProcessManager,
    registry: ToolRegistry,
):
    """Lifespan that publishes reconciliation + daemon.started on startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        schema = storage.schema_migration()

        # Reconcile orphan processes, then sweep any project left stuck in a
        # running state with no live process (Contract #6).
        outcomes = await asyncio.to_thread(reconcile, storage.conn)
        await asyncio.to_thread(reconcile_project_statuses, storage.conn)
        await boot_publish_reconciliation(bus, outcomes)
        await boot_publish_daemon_started(bus, schema)

        # Load tool plugin manifests (Milestone F plugin system) + start the
        # watchdog so a manifest dropped into tools/ shows up live (v0.1.21).
        loaded = await asyncio.to_thread(registry.load)
        if loaded:
            log.info("Loaded %d tool(s): %s", len(loaded), loaded)
        registry.start_watching(asyncio.get_running_loop())

        # Start the resource heartbeat loop (Contract #19).
        pm.start_monitoring()

        log.info(
            "Synapse daemon %s ready | schema=%d | contracts 1-28 | port=%d",
            __version__,
            schema,
            app.state.bound_port,
        )
        yield
        log.info("Synapse daemon shutting down.")
        await registry.shutdown_all()
        # Close every live PTY session before the loop tears down -- the
        # session manager rides on app.state (wired in build_app).
        pty_manager = getattr(app.state, "pty_manager", None)
        if pty_manager is not None:
            await pty_manager.shutdown_all()
        pm.shutdown()

    return lifespan


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    _configure_logging(args.log_level)

    assert_not_admin(allow_admin=args.allow_admin)

    # Read the persisted boot config -- the Settings → Network panel
    # writes this; if the user toggled "Allow LAN" in the UI we honour
    # it on the next start. CLI --bind-lan still wins so a one-off
    # debug session doesn't get blocked by the persisted preference.
    boot_cfg = boot_config.load(args.data_dir)
    host = args.host
    if args.bind_lan or boot_cfg.bind_lan:
        host = LAN_HOST
    log.info(
        "Listening on %s:%d (bind_lan=%s, source=%s)",
        host,
        args.port,
        host == LAN_HOST,
        "cli" if args.bind_lan else ("config" if boot_cfg.bind_lan else "default"),
    )

    storage = Storage(args.data_dir)
    storage.open()
    applied = storage.migrate()
    if applied:
        log.info("Applied %d migration(s): %s", len(applied), applied)

    seeded = seed_default_projects(storage)
    if seeded:
        log.info("Seeded default project(s): %s", seeded)

    bus = EventBus()
    pm = ProcessManager(storage, bus)
    registry = ToolRegistry(args.tools_dir, bus, storage)
    auth = AuthManager(storage, ensure_local_token(storage.data_dir))
    app = build_app(
        storage, bus, process_manager=pm, tool_registry=registry, auth=auth
    )
    app.state.bound_port = args.port
    app.state.bound_host = host
    app.state.data_dir = args.data_dir
    app.router.lifespan_context = _build_lifespan(storage, bus, pm, registry)

    try:
        uvicorn.run(
            app,
            host=host,
            port=args.port,
            log_level=args.log_level,
            access_log=False,           # daemon writes its own audit log
            lifespan="on",
        )
    finally:
        pm.shutdown()
        storage.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
