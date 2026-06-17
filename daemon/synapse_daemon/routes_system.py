"""System-level routes: network bind, restart hints, etc. (v0.1.35).

  GET   /api/v1/system/network
        Return: current bind host, all detectable LAN IPv4 addresses,
        whether the persisted ``bind_lan`` config flag is set,
        and a hint about whether the user needs to restart to apply.

  PATCH /api/v1/system/network
        Body: ``{ "bind_lan": true | false }``.
        Writes the persisted boot_config.json. Does NOT rebind the
        running uvicorn -- that needs a daemon restart. Response
        includes ``restart_required: true`` when the new value
        differs from the live bind.

Why a separate file: the existing routers are tied to domain entities
(projects, tools, sessions). System-level controls don't fit there.
Add settings here as they get UIs.
"""

from __future__ import annotations

import logging
import socket
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from . import boot_config
from .audit import AuditRecord, audit
from .models import AuditSource
from .storage import Storage

log = logging.getLogger(__name__)

LAN_HOST = "0.0.0.0"
LOOPBACK_HOST = "127.0.0.1"


def _detect_lan_ips() -> list[str]:
    """Return every non-loopback IPv4 address the OS reports for the
    machine. ``hostname -I`` is the unix equivalent; we use socket so
    we have one cross-platform path.

    Best-effort: a transient DNS error returns an empty list rather
    than raising. The UI uses the result as a hint, not a contract.
    """

    addrs: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            ip = info[4][0]
            if ip and ip != "127.0.0.1":
                addrs.add(ip)
    except OSError as exc:  # pragma: no cover -- transient
        log.debug("hostname-based LAN lookup failed: %s", exc)
    # ``socket.getaddrinfo`` may miss interface IPs; iterate the
    # interfaces too. Avoid psutil dependency -- use the UDP trick:
    # connect a UDP socket to a public address (no packet is sent for
    # UDP-connect) and read back the local endpoint the OS chose.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.05)
            s.connect(("8.8.8.8", 53))
            ip = s.getsockname()[0]
            if ip and ip != "127.0.0.1":
                addrs.add(ip)
    except OSError as exc:  # pragma: no cover -- no route
        log.debug("UDP-trick LAN lookup failed: %s", exc)
    return sorted(addrs)


class NetworkPatch(BaseModel):
    bind_lan: bool


def build_system_router(storage: Storage, data_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/system", tags=["system"])

    @router.get("/network", response_model=None)
    async def get_network(request: Request) -> dict[str, Any]:
        cfg = boot_config.load(data_dir)
        # The actual live bind is encoded on app.state by __main__ (sort
        # of -- not yet wired). Fall back to inferring from headers if
        # not present.
        live_host = getattr(request.app.state, "bound_host", None) or LOOPBACK_HOST
        port = getattr(request.app.state, "bound_port", 7878)
        lan_ips = _detect_lan_ips() if live_host == LAN_HOST else _detect_lan_ips()
        return {
            "bind_lan_persisted": cfg.bind_lan,
            "bound_host": live_host,
            "bound_port": port,
            "lan_ips": lan_ips,
            "mobile_urls": [
                f"http://{ip}:{port}/mobile" for ip in lan_ips
            ] if live_host == LAN_HOST else [],
            "loopback_url": f"http://localhost:{port}/mobile",
            "restart_required": cfg.bind_lan != (live_host == LAN_HOST),
        }

    @router.patch("/network", response_model=None)
    async def patch_network(
        payload: NetworkPatch, request: Request
    ) -> dict[str, Any]:
        cfg = boot_config.load(data_dir)
        previous = cfg.bind_lan
        cfg.bind_lan = payload.bind_lan
        boot_config.save(data_dir, cfg)
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="system",
                    entity_id="network",
                    action="network.bind_lan.set",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"previous": previous, "current": payload.bind_lan},
                ),
            )
        live_host = getattr(request.app.state, "bound_host", None) or LOOPBACK_HOST
        return {
            "bind_lan_persisted": cfg.bind_lan,
            "bound_host": live_host,
            "restart_required": cfg.bind_lan != (live_host == LAN_HOST),
        }

    return router
