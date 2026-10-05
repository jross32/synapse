"""Targeted Synapse daemon recovery that preserves managed project processes.

Used by the daemon watchdog and the one-click operator recovery path. The old
watchdog used taskkill /T /F on the daemon root. One inaccessible descendant
could make taskkill fail the whole operation, leaving port 7878 owned forever;
conversely, a successful tree kill could also terminate healthy Synapse-managed
project children. This helper snapshots Synapse active managed-process rows,
preserves those live subtrees, terminates only unregistered daemon descendants,
and always terminates the verified synapse_daemon root itself.
"""

from __future__ import annotations

import argparse
import json
import socket
import sqlite3
import time
from pathlib import Path

import psutil


def _live_managed_pids(db_path: Path) -> set[int]:
    if not db_path.is_file():
        return set()
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return set()
    try:
        rows = conn.execute(
            "SELECT pid FROM managed_processes "
            "WHERE stopped_at IS NULL AND status = 'launched'"
        ).fetchall()
    except sqlite3.Error:
        return set()
    finally:
        conn.close()

    preserve: set[int] = set()
    for (raw_pid,) in rows:
        try:
            proc = psutil.Process(int(raw_pid))
            preserve.add(proc.pid)
            preserve.update(child.pid for child in proc.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, TypeError):
            continue
    return preserve


def _verified_daemon_pid(port: int) -> int | None:
    try:
        connections = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, OSError):
        return None
    for conn in connections:
        if conn.status != psutil.CONN_LISTEN or not conn.laddr:
            continue
        if int(conn.laddr.port) != int(port) or not conn.pid:
            continue
        try:
            proc = psutil.Process(conn.pid)
            command = " ".join(proc.cmdline()).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "synapse_daemon" in command:
            return proc.pid
    return None


def _port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        try:
            return sock.connect_ex(("127.0.0.1", int(port))) == 0
        except OSError:
            return False


def recover(port: int, data_dir: Path) -> dict[str, object]:
    root_pid = _verified_daemon_pid(port)
    if root_pid is None:
        occupied = _port_listening(port)
        return {
            "ok": not occupied,
            "daemon_pid": None,
            "port_released": not occupied,
            "detail": (
                f"No process is listening on port {port}."
                if not occupied
                else (
                    f"Port {port} is occupied but its owner could not be verified as "
                    "synapse_daemon; refusing a duplicate or destructive restart."
                )
            ),
            "preserved_managed_pids": [],
            "terminated_descendants": [],
        }

    try:
        root = psutil.Process(root_pid)
        descendants = root.children(recursive=True)
    except psutil.NoSuchProcess:
        return {
            "ok": True,
            "daemon_pid": root_pid,
            "detail": "Daemon exited before recovery began.",
            "preserved_managed_pids": [],
            "terminated_descendants": [],
        }

    preserve = _live_managed_pids(data_dir / "synapse.sqlite")

    # If recovery was itself launched through synapse_run_command, this helper and
    # its PowerShell launcher are descendants of the daemon being replaced. Preserve
    # that narrow current-process lineage so the recovery script can finish, launch
    # the replacement daemon, and write its result after the old daemon exits.
    current_lineage: set[int] = set()
    try:
        current = psutil.Process()
        while current.pid != root_pid:
            current_lineage.add(current.pid)
            parent = current.parent()
            if parent is None:
                break
            current = parent
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    preserve.update(current_lineage)

    preserved_descendants = sorted(proc.pid for proc in descendants if proc.pid in preserve)
    targets = [proc for proc in descendants if proc.pid not in preserve]

    # Terminate unregistered descendants leaf-first. Failures are isolated per
    # process: one inaccessible/stale PID must never block the root daemon stop.
    for proc in reversed(targets):
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _gone, alive = psutil.wait_procs(targets, timeout=1.0)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if alive:
        psutil.wait_procs(alive, timeout=1.0)

    root_terminated = False
    try:
        root.terminate()
        root.wait(timeout=2.0)
        root_terminated = True
    except psutil.TimeoutExpired:
        try:
            root.kill()
            root.wait(timeout=2.0)
            root_terminated = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            root_terminated = not psutil.pid_exists(root_pid)
    except psutil.NoSuchProcess:
        root_terminated = True
    except psutil.AccessDenied:
        root_terminated = False

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and _verified_daemon_pid(port) is not None:
        time.sleep(0.1)
    port_released = _verified_daemon_pid(port) is None

    return {
        "ok": bool(root_terminated and port_released),
        "daemon_pid": root_pid,
        "root_terminated": root_terminated,
        "port_released": port_released,
        "preserved_managed_pids": preserved_descendants,
        "terminated_descendants": sorted(proc.pid for proc in targets),
    }


def stop_legacy_watchdogs() -> list[int]:
    """Stop only the superseded PowerShell daemon-watchdog instances."""
    stopped: list[int] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = str(proc.info.get("name") or "").lower()
            command = " ".join(proc.info.get("cmdline") or []).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "powershell" not in name:
            continue
        if "daemon-watchdog.ps1" not in command:
            continue
        if "daemon-watchdog-v2.ps1" in command:
            continue
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
            stopped.append(proc.pid)
        except psutil.TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=1.0)
                stopped.append(proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(stopped)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7878)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--stop-legacy-watchdogs",
        action="store_true",
        help="Also stop superseded daemon-watchdog.ps1 PowerShell instances.",
    )
    args = parser.parse_args()
    stopped_watchdogs = stop_legacy_watchdogs() if args.stop_legacy_watchdogs else []
    result = recover(args.port, args.data_dir.resolve())
    result["stopped_legacy_watchdogs"] = stopped_watchdogs
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
