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

import asyncio
import json
import logging
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from . import boot_config
from .api_versions import event_name
from .audit import AuditRecord, audit
from .models import AuditSource
from .storage import Storage
from .time_utils import to_iso, utc_now

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


class RemoteAccessNetwork(BaseModel):
    bind_lan_persisted: bool
    bound_host: str
    bound_port: int
    lan_ips: list[str]
    mobile_urls: list[str]
    loopback_url: str
    restart_required: bool


class RemoteAccessPairingCode(BaseModel):
    active: bool
    code: str | None = None
    expires_at: str | None = None


class RemoteAccessDevice(BaseModel):
    id: str
    name: str
    created_at: str
    last_seen_at: str | None = None


class RemoteAccessWanVerification(BaseModel):
    status: str
    checked_at: str | None = None
    health_url: str | None = None
    mobile_url: str | None = None
    health_ok: bool = False
    mobile_ok: bool = False
    failure_code: str | None = None
    failure_message: str | None = None


class RemoteAccessWan(BaseModel):
    available: bool
    active: bool
    tunnel_id: str | None = None
    public_url: str | None = None
    local_port: int | None = None
    label: str | None = None
    verification: RemoteAccessWanVerification


class RemoteAccessResponse(BaseModel):
    computer_name: str
    network: RemoteAccessNetwork
    pairing_code: RemoteAccessPairingCode
    paired_devices: list[RemoteAccessDevice] = Field(default_factory=list)
    wan: RemoteAccessWan


def _computer_name() -> str:
    return socket.gethostname() or "This computer"


def _network_status(request: Request, data_dir: Path) -> dict[str, Any]:
    cfg = boot_config.load(data_dir)
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


def _cloudtap_entry(request: Request) -> tuple[bool, Any | None]:
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is None:
        return False, None
    try:
        registry.get_manifest("cloudtap")
    except Exception:
        return False, None
    try:
        return True, registry.get_state("cloudtap")
    except Exception:
        return True, None


def _probe_remote_url(
    url: str,
    *,
    expect_json_ok: bool = False,
    expect_text: str | None = None,
    timeout_seconds: float = 12.0,
) -> tuple[bool, str | None, str | None]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json, text/html;q=0.9, */*;q=0.8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None) or response.getcode()
            if status != 200:
                return False, "http_status", f"HTTP {status} from {url}"
            body = response.read(4096)
    except urllib.error.HTTPError as exc:
        return False, "http_status", f"HTTP {exc.code} from {url}"
    except urllib.error.URLError as exc:
        return False, "unreachable", f"Could not reach {url}: {exc.reason}"
    except OSError as exc:
        return False, "unreachable", f"Could not reach {url}: {exc}"

    if expect_json_ok:
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:
            return False, "invalid_json", f"{url} did not return valid JSON."
        if not isinstance(parsed, dict) or parsed.get("ok") is not True:
            return False, "unexpected_payload", f"{url} did not report ok=true."

    if expect_text is not None:
        text = body.decode("utf-8", errors="replace")
        if expect_text not in text:
            return False, "unexpected_payload", f"{url} did not look like the Synapse mobile shell."

    return True, None, None


async def _verify_public_tunnel(public_url: str) -> RemoteAccessWanVerification:
    base = str(public_url).rstrip("/")
    health_url = f"{base}/api/v1/health"
    mobile_url = f"{base}/mobile"

    health_ok, health_code, health_message = await asyncio.to_thread(
        _probe_remote_url,
        health_url,
        expect_json_ok=True,
        timeout_seconds=8.0,
    )
    if not health_ok:
        return RemoteAccessWanVerification(
            status="error",
            checked_at=to_iso(utc_now()),
            health_url=health_url,
            mobile_url=mobile_url,
            health_ok=False,
            mobile_ok=False,
            failure_code=health_code,
            failure_message=health_message,
        )

    mobile_ok, mobile_code, mobile_message = await asyncio.to_thread(
        _probe_remote_url,
        mobile_url,
        expect_text="Synapse",
        timeout_seconds=15.0,
    )

    if not mobile_ok:
        return RemoteAccessWanVerification(
            status="error",
            checked_at=to_iso(utc_now()),
            health_url=health_url,
            mobile_url=mobile_url,
            health_ok=True,
            mobile_ok=False,
            failure_code=mobile_code,
            failure_message=mobile_message,
        )

    return RemoteAccessWanVerification(
        status="ready",
        checked_at=to_iso(utc_now()),
        health_url=health_url,
        mobile_url=mobile_url,
        health_ok=True,
        mobile_ok=True,
    )


def build_system_router(storage: Storage, data_dir: Path) -> APIRouter:
    router = APIRouter(tags=["system"])

    @router.get("/system/network", response_model=None)
    async def get_network(request: Request) -> dict[str, Any]:
        return _network_status(request, data_dir)

    @router.get("/remote-access", response_model=RemoteAccessResponse)
    async def get_remote_access(request: Request) -> RemoteAccessResponse:
        network = RemoteAccessNetwork.model_validate(_network_status(request, data_dir))
        auth = request.app.state.auth
        pairing_code = auth.current_code()
        code_status = RemoteAccessPairingCode(
            active=pairing_code is not None,
            code=pairing_code["code"] if pairing_code else None,
            expires_at=pairing_code["expires_at"] if pairing_code else None,
        )

        cloudtap_available, cloudtap_state = _cloudtap_entry(request)
        daemon_tunnel = None
        stray_tunnel = None
        if cloudtap_state is not None:
            daemon_tunnel = next(
                (
                    item
                    for item in cloudtap_state.items
                    if item.result.get("local_port") == network.bound_port
                ),
                None,
            )
            stray_tunnel = cloudtap_state.items[0] if cloudtap_state.items else None

        if not cloudtap_available:
            wan = RemoteAccessWan(
                available=False,
                active=False,
                verification=RemoteAccessWanVerification(
                    status="unavailable",
                    failure_code="cloudtap.unavailable",
                    failure_message="Cloudtap is not installed in this Synapse build.",
                ),
            )
        elif daemon_tunnel is None:
            wan = RemoteAccessWan(
                available=True,
                active=False,
                verification=RemoteAccessWanVerification(
                    status="error" if stray_tunnel is not None else "inactive",
                    failure_code="cloudtap.wrong_port" if stray_tunnel is not None else "cloudtap.inactive",
                    failure_message=(
                        f"Cloudtap is exposing port {stray_tunnel.result.get('local_port')}, but "
                        f"Synapse is bound to {network.bound_port}."
                    ) if stray_tunnel is not None else "No WAN tunnel is open for Synapse right now.",
                ),
            )
        else:
            public_url = daemon_tunnel.result.get("public_url")
            local_port = daemon_tunnel.result.get("local_port")
            if not isinstance(public_url, str):
                verification = RemoteAccessWanVerification(
                    status="error",
                    failure_code="cloudtap.no_public_url",
                    failure_message="Cloudtap has not produced a public URL yet.",
                )
            elif local_port != network.bound_port:
                verification = RemoteAccessWanVerification(
                    status="error",
                    failure_code="cloudtap.wrong_port",
                    failure_message=(
                        f"Cloudtap is exposing port {local_port}, but Synapse is bound to "
                        f"{network.bound_port}."
                    ),
                )
            else:
                verification = await _verify_public_tunnel(public_url)

            wan = RemoteAccessWan(
                available=True,
                active=True,
                tunnel_id=daemon_tunnel.id,
                public_url=public_url if isinstance(public_url, str) else None,
                local_port=local_port if isinstance(local_port, int) else None,
                label=daemon_tunnel.label,
                verification=verification,
            )

        return RemoteAccessResponse(
            computer_name=_computer_name(),
            network=network,
            pairing_code=code_status,
            paired_devices=[
                RemoteAccessDevice.model_validate(device)
                for device in auth.list_devices()
            ],
            wan=wan,
        )

    @router.patch("/system/network", response_model=None)
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
        await request.app.state.bus.publish(
            event_name("remote_access", "updated"),
            {"reason": "network-bind-updated"},
        )
        live_host = getattr(request.app.state, "bound_host", None) or LOOPBACK_HOST
        return {
            "bind_lan_persisted": cfg.bind_lan,
            "bound_host": live_host,
            "restart_required": cfg.bind_lan != (live_host == LAN_HOST),
        }

    return router
