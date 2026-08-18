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
import secrets
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from . import boot_config
from .api_versions import event_name
from .audit import AuditRecord, audit
from .errors import conflict, not_found
from .models import AuditSource
from .storage import Storage
from .time_utils import to_iso, utc_now

log = logging.getLogger(__name__)

LAN_HOST = "0.0.0.0"
LOOPBACK_HOST = "127.0.0.1"
CLOUDTAP_WARMUP_GRACE_SECONDS = 90
RESTART_STAGE_KEYS = ("request", "stop", "desktop", "daemon", "interface")
RESTART_ERROR_CODES = {
    "SYN-RST-001": "A restart is already running. Wait for the current restart window to finish.",
    "SYN-RST-101": "Synapse could not stop its previous services cleanly.",
    "SYN-RST-201": "Electron could not schedule or hand off the relaunch.",
    "SYN-BOOT-101": "The Synapse daemon process could not be started.",
    "SYN-BOOT-102": "The Synapse daemon started but did not become healthy in time.",
    "SYN-BOOT-201": "The desktop interface could not be loaded.",
    "SYN-BOOT-202": "The desktop interface loaded but never became ready to show.",
    "SYN-BOOT-301": "The saved restart progress record was invalid or unreadable.",
}


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
    # Both optional so a caller can toggle just one knob (e.g. the WAN switch sends
    # only `wan_auto_start`). A field left None is untouched.
    bind_lan: bool | None = None
    wan_auto_start: bool | None = None
    mcp_writes_enabled: bool | None = None


class RestartRequest(BaseModel):
    operation_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9._-]{6,80}$",
    )
    source: AuditSource = AuditSource.AUTO


class RestartStageUpdate(BaseModel):
    stage: Literal["request", "stop", "desktop", "daemon", "interface"]
    state: Literal["pending", "active", "success", "error"]
    detail: str = Field(min_length=1, max_length=1000)
    error_code: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=4000)
    source: AuditSource = AuditSource.DESKTOP


def _loads_restart_details(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value) if value else {}
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _restart_operation(storage: Storage, operation_id: str | None = None) -> dict[str, Any] | None:
    params: list[Any] = []
    where = "entity_type = 'system_restart' AND action = 'restart.requested'"
    if operation_id is not None:
        where += " AND entity_id = ?"
        params.append(operation_id)
    request_row = storage.conn.execute(
        f"SELECT * FROM audit_log WHERE {where} ORDER BY id DESC LIMIT 1",
        tuple(params),
    ).fetchone()
    if request_row is None:
        return None

    operation_id = str(request_row["entity_id"])
    request_details = _loads_restart_details(request_row["details_json"])
    stages: dict[str, dict[str, Any]] = {
        key: {
            "stage": key,
            "state": "pending",
            "detail": "Waiting",
            "updated_at": request_row["timestamp_utc"],
            "error_code": None,
            "error_message": None,
        }
        for key in RESTART_STAGE_KEYS
    }
    rows = storage.conn.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'system_restart' AND entity_id = ? "
        "AND action = 'restart.stage' ORDER BY id",
        (operation_id,),
    ).fetchall()
    terminal_error_seen = False
    for row in rows:
        details = _loads_restart_details(row["details_json"])
        stage = details.get("stage")
        if stage not in stages:
            continue
        # Restart errors are terminal for one operation. Electron readiness
        # callbacks may arrive after a timeout; retain the first truthful
        # failure instead of allowing a later success row to paint it green.
        if terminal_error_seen:
            continue
        stages[stage] = {
            "stage": stage,
            "state": details.get("state", "pending"),
            "detail": details.get("detail", "Waiting"),
            "updated_at": row["timestamp_utc"],
            "error_code": row["error_code"],
            "error_message": details.get("error_message"),
        }
        terminal_error_seen = details.get("state") == "error"

    ordered = [stages[key] for key in RESTART_STAGE_KEYS]
    states = {stage["state"] for stage in ordered}
    if "error" in states:
        status = "error"
    elif all(stage["state"] == "success" for stage in ordered):
        status = "complete"
    elif rows:
        status = "restarting"
    else:
        status = "requested"
    try:
        updated_at = datetime.fromisoformat(
            rows[-1]["timestamp_utc"] if rows else request_row["timestamp_utc"]
        )
        if status in {"requested", "restarting"} and updated_at < utc_now() - timedelta(minutes=10):
            status = "error"
            stalled_stage = next(
                (stage for stage in ordered if stage["state"] in {"pending", "active"}),
                ordered[-1],
            )
            stalled_stage.update(
                {
                    "state": "error",
                    "detail": "Restart progress expired before this stage completed.",
                    "error_code": "SYN-BOOT-301",
                    "error_message": "No restart progress was reported for more than ten minutes.",
                }
            )
    except (TypeError, ValueError):
        pass
    return {
        "operation_id": operation_id,
        "source": request_details.get("source", request_row["source"]),
        "status": status,
        "requested_at": request_row["timestamp_utc"],
        "updated_at": rows[-1]["timestamp_utc"] if rows else request_row["timestamp_utc"],
        "stages": ordered,
    }


class RemoteAccessNetwork(BaseModel):
    bind_lan_persisted: bool
    wan_auto_start: bool = True
    mcp_writes_enabled: bool = True
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
        "wan_auto_start": cfg.wan_auto_start,
        "mcp_writes_enabled": cfg.mcp_writes_enabled,
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


def _apply_cloudtap_warmup_grace(
    verification: RemoteAccessWanVerification,
    *,
    created_at,
) -> RemoteAccessWanVerification:
    if verification.status != "error":
        return verification
    if created_at is None:
        return verification
    age = utc_now() - created_at
    if age > timedelta(seconds=CLOUDTAP_WARMUP_GRACE_SECONDS):
        return verification
    if verification.failure_code not in {"unreachable", "http_status", "invalid_json", "unexpected_payload"}:
        return verification
    return verification.model_copy(
        update={
            "status": "warming",
            "failure_message": (
                "Cloudtap is still warming up and DNS/mobile checks can lag for a minute. "
                f"Latest probe: {verification.failure_message}"
            ),
        }
    )


def build_system_router(storage: Storage, data_dir: Path) -> APIRouter:
    router = APIRouter(tags=["system"])

    @router.get("/system/network", response_model=None)
    async def get_network(request: Request) -> dict[str, Any]:
        return _network_status(request, data_dir)

    @router.get("/system/restart", response_model=None)
    async def get_restart_operation() -> dict[str, Any]:
        return {
            "operation": _restart_operation(storage),
            "error_catalog": RESTART_ERROR_CODES,
        }

    @router.get("/system/restart/errors", response_model=None)
    async def get_restart_error_catalog() -> dict[str, Any]:
        return {"error_catalog": RESTART_ERROR_CODES}

    @router.post("/system/restart", response_model=None, status_code=202)
    async def request_restart(payload: RestartRequest, request: Request) -> dict[str, Any]:
        latest = _restart_operation(storage)
        if latest is not None and latest["status"] in {"requested", "restarting"}:
            raise conflict(
                "system_restart",
                "A Synapse restart is already in progress.",
                operation_id=latest["operation_id"],
                diagnostic_code="SYN-RST-001",
            )
        operation_id = payload.operation_id or f"restart-{secrets.token_hex(6)}"
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="system_restart",
                    entity_id=operation_id,
                    action="restart.requested",
                    source=payload.source,
                    result="success",
                    details={"source": payload.source.value},
                ),
            )
        await request.app.state.bus.publish(
            event_name("system", "restart_requested"),
            {
                "operation_id": operation_id,
                "source": payload.source.value,
            },
        )
        return {
            "operation": _restart_operation(storage, operation_id),
            "error_catalog": RESTART_ERROR_CODES,
        }

    @router.post("/system/restart/{operation_id}/stage", response_model=None)
    async def report_restart_stage(
        operation_id: str,
        payload: RestartStageUpdate,
        request: Request,
    ) -> dict[str, Any]:
        if _restart_operation(storage, operation_id) is None:
            raise not_found("system_restart", operation_id)
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="system_restart",
                    entity_id=operation_id,
                    action="restart.stage",
                    source=payload.source,
                    result="error" if payload.state == "error" else "success",
                    error_code=payload.error_code,
                    details={
                        "stage": payload.stage,
                        "state": payload.state,
                        "detail": payload.detail,
                        "error_message": payload.error_message,
                    },
                ),
            )
        operation = _restart_operation(storage, operation_id)
        await request.app.state.bus.publish(
            event_name("system", "restart_progress"),
            {"operation": operation},
        )
        return {
            "operation": operation,
            "error_catalog": RESTART_ERROR_CODES,
        }

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
                verification = _apply_cloudtap_warmup_grace(
                    verification,
                    created_at=daemon_tunnel.created_at,
                )

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
        changes: dict[str, dict[str, bool]] = {}
        if payload.bind_lan is not None and payload.bind_lan != cfg.bind_lan:
            changes["bind_lan"] = {"previous": cfg.bind_lan, "current": payload.bind_lan}
            cfg.bind_lan = payload.bind_lan
        if payload.wan_auto_start is not None and payload.wan_auto_start != cfg.wan_auto_start:
            changes["wan_auto_start"] = {"previous": cfg.wan_auto_start, "current": payload.wan_auto_start}
            cfg.wan_auto_start = payload.wan_auto_start
        if (payload.mcp_writes_enabled is not None
                and payload.mcp_writes_enabled != cfg.mcp_writes_enabled):
            changes["mcp_writes_enabled"] = {"previous": cfg.mcp_writes_enabled,
                                             "current": payload.mcp_writes_enabled}
            cfg.mcp_writes_enabled = payload.mcp_writes_enabled
        if changes:
            boot_config.save(data_dir, cfg)
            with storage.transaction() as conn:
                for key, delta in changes.items():
                    audit(
                        conn,
                        AuditRecord(
                            entity_type="system",
                            entity_id="network",
                            action=f"network.{key}.set",
                            source=AuditSource.DESKTOP,
                            result="success",
                            details=delta,
                        ),
                    )
            await request.app.state.bus.publish(
                event_name("remote_access", "updated"),
                {"reason": "network-updated"},
            )
        live_host = getattr(request.app.state, "bound_host", None) or LOOPBACK_HOST
        return {
            "bind_lan_persisted": cfg.bind_lan,
            "wan_auto_start": cfg.wan_auto_start,
            "mcp_writes_enabled": cfg.mcp_writes_enabled,
        "mcp_writes_enabled": cfg.mcp_writes_enabled,
            "bound_host": live_host,
            "restart_required": cfg.bind_lan != (live_host == LAN_HOST),
        }

    return router
