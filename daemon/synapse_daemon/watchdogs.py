"""Watchdog and background-service inventory for the Synapse dashboard.

This module is intentionally read-only. It discovers the protection chain from
known process signatures plus Windows Scheduled Tasks and exposes safe log tails.
Future services can be added without changing the UI by extending DEFAULT_SPECS.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

import psutil

_CACHE_LOCK = Lock()
_CACHE_AT = 0.0
_CACHE_VALUE: dict[str, Any] | None = None
_CACHE_TTL_SECONDS = 2.0


@dataclass(frozen=True)
class WatchdogSpec:
    id: str
    name: str
    kind: str
    description: str
    command_any: tuple[tuple[str, ...], ...] = ()
    task_names: tuple[str, ...] = ()
    protects: tuple[str, ...] = ()
    log_path: Path | None = None
    expected_long_running: bool = True
    group: str = "system"
    tags: tuple[str, ...] = field(default_factory=tuple)
    background_safe: bool = True


def _stock_runtime_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "StockHunter"
    return Path.home() / ".stock-hunter"


def _scraper_root() -> Path:
    return Path.home() / "wbscrper"


def _latest_file(root: Path, pattern: str) -> Path | None:
    try:
        candidates = [path for path in root.glob(pattern) if path.is_file()]
        return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None
    except OSError:
        return None


def default_specs(data_dir: Path) -> list[WatchdogSpec]:
    stock_runtime = _stock_runtime_root()
    scraper = _scraper_root()
    scraper_log = _latest_file(data_dir / "logs" / "wbscrper", "*.log")
    return [
        WatchdogSpec(
            id="synapse-daemon",
            name="Synapse Daemon",
            kind="service",
            description="Core Synapse API and orchestration daemon.",
            command_any=(("python", "-m", "synapse_daemon", "--port", "7878"),),
            log_path=data_dir / "daemon-runtime.log",
            group="synapse",
            tags=("core", "api"),
        ),
        WatchdogSpec(
            id="synapse-daemon-watchdog",
            name="Synapse Daemon Watchdog",
            kind="watchdog",
            description="Checks Synapse health and performs bounded daemon recovery.",
            command_any=(("powershell", "daemon-watchdog.ps1"),),
            protects=("synapse-daemon",),
            log_path=data_dir / "daemon-watchdog.log",
            group="synapse",
            tags=("recovery",),
        ),
        WatchdogSpec(
            id="synapse-tunnel",
            name="Synapse Cloudflare Tunnel",
            kind="service",
            description="Persistent Cloudflare tunnel used for remote Synapse access.",
            command_any=(("cloudflared", "tunnel", "run", "synapse"),),
            group="synapse",
            tags=("network", "remote"),
        ),
        WatchdogSpec(
            id="synapse-tunnel-watchdog",
            name="Synapse Tunnel Watchdog",
            kind="watchdog",
            description="Checks the public tunnel and restarts cloudflared after bounded failures.",
            command_any=(("powershell", "tunnel-watchdog.ps1"),),
            protects=("synapse-tunnel",),
            log_path=data_dir / "tunnel-watchdog.log",
            group="synapse",
            tags=("recovery", "network"),
        ),
        WatchdogSpec(
            id="synapse-ai-supervisor",
            name="Synapse AI Supervisor",
            kind="supervisor",
            description="Observes AI sessions, work items, monitor health, and meaningful events.",
            command_any=(("python", str(data_dir / "ai-supervisor" / "supervisor.py").lower()),),
            task_names=("Synapse AI Supervisor",),
            log_path=data_dir / "ai-supervisor" / "supervisor-events.jsonl",
            group="synapse",
            tags=("ai", "orchestration"),
        ),
        WatchdogSpec(
            id="synapse-live-monitor",
            name="Synapse Live Monitor",
            kind="monitor",
            description="Collects lightweight process, focus, network, resource, and Windows-event telemetry.",
            command_any=(("powershell", str(data_dir / "live-monitor" / "live-monitor.ps1").lower()),),
            task_names=("Synapse Live Monitor",),
            log_path=data_dir / "live-monitor" / "events.jsonl",
            group="synapse",
            tags=("telemetry",),
        ),
        WatchdogSpec(
            id="synapse-repair-watchdog",
            name="Synapse Repair Watchdog",
            kind="watchdog",
            description="Periodically verifies Live Monitor and AI Supervisor heartbeats and restarts stale tasks.",
            command_any=(("python", str(data_dir / "system-watchdog" / "repair_watchdog.py").lower()),),
            task_names=("Synapse Repair Watchdog",),
            protects=("synapse-live-monitor", "synapse-ai-supervisor"),
            log_path=data_dir / "system-watchdog" / "watchdog-events.jsonl",
            expected_long_running=False,
            group="synapse",
            tags=("recovery", "heartbeat"),
        ),
        WatchdogSpec(
            id="stock-hunter-mcp",
            name="Stock Hunter MCP Service",
            kind="service",
            description="Stock Hunter HTTP/MCP research runtime on loopback.",
            command_any=(("python", "-m", "stock_hunter.http_service"),),
            log_path=stock_runtime / "mcp-service-supervised.log",
            group="stock-hunter",
            tags=("mcp", "research"),
        ),
        WatchdogSpec(
            id="stock-hunter-supervisor",
            name="Stock Hunter Supervisor",
            kind="supervisor",
            description="Checks the Stock Hunter MCP runtime identity and health, then performs bounded recovery.",
            command_any=(("python", "-m", "stock_hunter.runtime_supervisor", "serve"),),
            task_names=("StockHunterSupervisor",),
            protects=("stock-hunter-mcp",),
            log_path=stock_runtime / "runtime-supervisor.jsonl",
            group="stock-hunter",
            tags=("recovery", "mcp"),
        ),
        WatchdogSpec(
            id="stock-hunter-supervisor-watchdog",
            name="Stock Hunter Supervisor Watchdog",
            kind="watchdog",
            description="Periodic self-watchdog that restarts the Stock Hunter Supervisor task if it was externally stopped.",
            command_any=(("python", "-m", "stock_hunter.runtime_supervisor", "ensure"),),
            task_names=("StockHunterSupervisorWatchdog",),
            protects=("stock-hunter-supervisor",),
            log_path=stock_runtime / "runtime-supervisor.jsonl",
            expected_long_running=False,
            group="stock-hunter",
            tags=("recovery",),
        ),
        WatchdogSpec(
            id="stock-hunter-daily-campaign",
            name="Stock Hunter Daily Research Campaign",
            kind="job",
            description="Scheduled prospective research cycle. It is research-only and is not a watchdog.",
            command_any=(("python", "-m", "stock_hunter.research_campaign", "run"),),
            task_names=("StockHunterDailyCampaign",),
            log_path=stock_runtime / "daily-campaign.jsonl",
            expected_long_running=False,
            group="stock-hunter",
            tags=("scheduled", "research"),
        ),
        WatchdogSpec(
            id="web-scraper-mcp",
            name="Web Scraper MCP Server",
            kind="service",
            description="wbscrper HTTP MCP server used by Synapse and AI workers.",
            command_any=(
                ("npm", "--prefix", str(scraper).lower(), "run", "mcp:http"),
                ("node", "mcp-server.js", "--http"),
            ),
            log_path=scraper_log,
            group="web-scraper",
            tags=("mcp", "web"),
        ),
    ]


def _process_inventory() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    now = time.time()
    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time", "status"]):
        try:
            info = proc.info
            cmdline = " ".join(str(part) for part in (info.get("cmdline") or []))
            name = str(info.get("name") or "")
            combined = f"{name} {cmdline}".strip()
            out.append(
                {
                    "pid": int(info["pid"]),
                    "name": name,
                    "command_line": cmdline,
                    "match_text": combined.lower(),
                    "status": str(info.get("status") or "unknown"),
                    "uptime_seconds": max(0, int(now - float(info.get("create_time") or now))),
                }
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, ValueError, TypeError):
            continue
    return out


def _match_processes(spec: WatchdogSpec, processes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not spec.command_any:
        return []
    matches: list[dict[str, Any]] = []
    for proc in processes:
        text = proc["match_text"]
        for group in spec.command_any:
            if all(token.lower() in text for token in group):
                matches.append({k: v for k, v in proc.items() if k != "match_text"})
                break
    return matches


def _tail(path: Path | None, lines: int = 8) -> list[str]:
    if path is None or not path.exists() or not path.is_file():
        return []
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            chunk = 8192
            data = b""
            while size > 0 and data.count(b"\n") <= lines:
                take = min(chunk, size)
                size -= take
                handle.seek(size)
                data = handle.read(take) + data
        return data.decode("utf-8", errors="replace").splitlines()[-lines:]
    except OSError:
        return []


def _latest_line(path: Path | None) -> str | None:
    lines = _tail(path, 1)
    return lines[-1] if lines else None


def _task_inventory(task_names: list[str]) -> dict[str, dict[str, Any]]:
    """Fast, non-blocking scheduled-task inventory hook.

    Live dashboard refreshes deliberately do not shell out to Task Scheduler,
    because schtasks can stall for seconds when Windows is unhealthy. Keeping
    this hook separate lets diagnostics/tests inject exact scheduler state and
    gives us a safe place to add a cached background collector later.
    """
    del task_names
    return {}


def _task_summary(
    spec: WatchdogSpec,
    matches: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return a fast task-shaped summary without blocking on Task Scheduler.

    The dashboard's live control-path truth is whether the expected process is
    present. Periodic watchdogs/jobs are intentionally idle between runs, so
    they are represented as Armed. Exact Task Scheduler history is available
    through Reflex/Windows diagnostics when needed; it should not add seconds
    of latency to every dashboard refresh.
    """
    if not spec.task_names:
        return None
    if matches:
        state = "Running"
    elif spec.expected_long_running:
        state = "Stopped"
    else:
        state = "Armed"
    return {
        "task_name": spec.task_names[0],
        "state": state,
        "hidden": spec.background_safe,
        "logon_mode": "background",
        "task_to_run": None,
        "last_run_time": None,
        "next_run_time": None,
        "last_task_result": None,
    }


def _health(
    spec: WatchdogSpec,
    matches: list[dict[str, Any]],
    task: dict[str, Any] | None,
) -> str:
    if matches:
        return "healthy"
    if task and not spec.expected_long_running:
        return "armed"
    return "stopped"


def snapshot_watchdogs(data_dir: Path, *, force: bool = False) -> dict[str, Any]:
    global _CACHE_AT, _CACHE_VALUE
    now = time.monotonic()
    with _CACHE_LOCK:
        if not force and _CACHE_VALUE is not None and now - _CACHE_AT < _CACHE_TTL_SECONDS:
            return _CACHE_VALUE

    specs = default_specs(data_dir)
    processes = _process_inventory()
    protected_by: dict[str, list[str]] = {}
    for spec in specs:
        for target in spec.protects:
            protected_by.setdefault(target, []).append(spec.id)

    task_names = sorted({name for spec in specs for name in spec.task_names})
    scheduled_tasks = _task_inventory(task_names)

    items: list[dict[str, Any]] = []
    for spec in specs:
        matches = _match_processes(spec, processes)
        task = next((scheduled_tasks[name] for name in spec.task_names if name in scheduled_tasks), None)
        if task is None:
            task = _task_summary(spec, matches)
        item = {
            "id": spec.id,
            "name": spec.name,
            "kind": spec.kind,
            "group": spec.group,
            "description": spec.description,
            "health": _health(spec, matches, task),
            "processes": matches,
            "task": task,
            "protects": list(spec.protects),
            "protected_by": protected_by.get(spec.id, []),
            "log_available": bool(spec.log_path and spec.log_path.exists()),
            "log_path": str(spec.log_path) if spec.log_path else None,
            "latest_log_line": _latest_line(spec.log_path),
            "tags": list(spec.tags),
            "console_risk": not spec.background_safe,
        }
        items.append(item)

    counts = {
        "total": len(items),
        "healthy": sum(item["health"] == "healthy" for item in items),
        "armed": sum(item["health"] == "armed" for item in items),
        "warning": sum(item["health"] == "warning" for item in items),
        "stopped": sum(item["health"] == "stopped" for item in items),
        "console_risk": sum(bool(item["console_risk"]) for item in items),
    }
    value = {
        "generated_at_epoch": time.time(),
        "counts": counts,
        "items": items,
    }
    with _CACHE_LOCK:
        _CACHE_AT = now
        _CACHE_VALUE = value
    return value


def watchdog_log(data_dir: Path, watchdog_id: str, lines: int = 120) -> dict[str, Any]:
    specs = {spec.id: spec for spec in default_specs(data_dir)}
    spec = specs.get(watchdog_id)
    if spec is None:
        raise KeyError(watchdog_id)
    safe_lines = max(1, min(int(lines), 500))
    return {
        "id": spec.id,
        "name": spec.name,
        "path": str(spec.log_path) if spec.log_path else None,
        "lines": _tail(spec.log_path, safe_lines),
    }
