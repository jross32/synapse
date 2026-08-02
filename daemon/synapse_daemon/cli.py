"""Synapse CLI (Contract #27).

A thin client over the daemon's REST API. Same commands, same data, same
audit log — no direct DB access. Commands map 1-to-1 with REST endpoints
defined in ``docs/api-changes.md``.

History:
- v0.1.2 shipped argparse plumbing + placeholder prints.
- v0.1.36 wired every command to the real daemon via
  :mod:`synapse_daemon.cli_http`. ``doctor`` is the only command that
  still runs without the daemon (it's the diagnostic that tells you
  *why* the daemon isn't answering).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections.abc import Sequence
from typing import Callable, NamedTuple

from . import __version__
from .cli_http import SynapseCliError, daemon_base, discover_token, print_json, request


# ── command handlers ─────────────────────────────────────────────────────


def _cmd_status(_args: argparse.Namespace) -> int:
    try:
        health = request("GET", "/health")
    except SynapseCliError as exc:
        print(f"synapse status: {exc}", file=sys.stderr)
        return 1
    print(
        f"synapse {__version__} · daemon v{health.get('version', '?')} "
        f"· started {health.get('started_at', '?')} · "
        f"{len(health.get('contracts', []))} contracts honoured"
    )
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    try:
        body = request("GET", "/projects")
    except SynapseCliError as exc:
        print(f"synapse list: {exc}", file=sys.stderr)
        return 1
    projects = body.get("projects", [])
    if not projects:
        print("(no projects registered)")
        return 0
    width = max(len(p["id"]) for p in projects)
    for p in projects:
        kind = p.get("kind", "app")
        port = p.get("expected_port")
        port_str = f":{port}" if port else ""
        print(
            f"  {p['id']:<{width}}  {p['status']:<10}  {kind:<10}  "
            f"{p.get('name', '')}{port_str}"
        )
    return 0


def _cmd_start(args: argparse.Namespace) -> int:
    try:
        result = request(
            "POST",
            f"/projects/{args.project_id}/launch",
            body={"source": "cli"},
        )
    except SynapseCliError as exc:
        print(f"synapse start: {exc}", file=sys.stderr)
        return 1
    print(f"{result['id']} -> {result['status']}")
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    try:
        result = request(
            "POST",
            f"/projects/{args.project_id}/stop",
            body={"source": "cli"},
        )
    except SynapseCliError as exc:
        print(f"synapse stop: {exc}", file=sys.stderr)
        return 1
    print(f"{result['id']} -> {result['status']}")
    return 0


def _cmd_logs(args: argparse.Namespace) -> int:
    try:
        seen = 0
        while True:
            payload = request(
                "GET",
                f"/projects/{args.project_id}/logs?lines={args.lines}",
            )
            lines = payload.get("lines", [])
            for line in lines[seen:]:
                print(line, end="" if line.endswith("\n") else "\n")
            seen = len(lines)
            if not args.follow:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    except SynapseCliError as exc:
        print(f"synapse logs: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_snapshot(args: argparse.Namespace) -> int:
    try:
        body = request("GET", "/snapshot/export")
    except SynapseCliError as exc:
        print(f"synapse snapshot: {exc}", file=sys.stderr)
        return 1
    output_path = args.output
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(body, fp, indent=2, default=str)
    print(f"Wrote {output_path}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    try:
        with open(args.input, "r", encoding="utf-8") as fp:
            snapshot = json.load(fp)
    except OSError as exc:
        print(f"synapse restore: could not read {args.input}: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"synapse restore: {args.input} is not valid JSON: {exc}", file=sys.stderr)
        return 1
    try:
        result = request("POST", "/snapshot/import", body=snapshot)
    except SynapseCliError as exc:
        print(f"synapse restore: {exc}", file=sys.stderr)
        return 1
    print(f"Restored {result.get('imported', '?')} entities.")
    return 0


# Ports Synapse owns: the daemon's API and the dev renderer.
SYNAPSE_PORTS: tuple[tuple[int, str], ...] = ((7878, "daemon API"), (5173, "renderer (Vite)"))

# Substrings that identify a process as *ours*. A holder that matches none of these
# is reported but never touched -- the port may simply belong to something else.
# Deliberately NOT a bare "synapse": every process started from a folder named
# `synapse` carries that in its cmdline, which would let `--fix` terminate an
# unrelated program that merely happens to live in this directory.
_SYNAPSE_CMDLINE_MARKERS = ("synapse_daemon", "synapse-daemon", "vite")


class PortHolder(NamedTuple):
    port: int
    label: str
    pid: int
    name: str
    cmdline: str
    is_synapse: bool


def find_port_holders(ports: Sequence[tuple[int, str]] = SYNAPSE_PORTS) -> list[PortHolder]:
    """Who is listening on each Synapse port right now?

    A stale Vite left on 5173 by a crashed run is what caused the launch failure
    fixed in 0.1.40, and a daemon that never released 7878 produces the same class
    of "it just won't start" confusion. `doctor` runs without the daemon, so this
    reads the OS directly rather than asking the API.
    """
    import psutil

    wanted = {port: label for port, label in ports}
    holders: list[PortHolder] = []
    seen: set[tuple[int, int]] = set()
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError):
        return []
    for conn in connections:
        if conn.status != psutil.CONN_LISTEN or not conn.laddr or conn.pid is None:
            continue
        port = conn.laddr.port
        if port not in wanted or (port, conn.pid) in seen:
            continue
        seen.add((port, conn.pid))
        name, cmdline = "?", ""
        try:
            proc = psutil.Process(conn.pid)
            name = proc.name()
            cmdline = " ".join(proc.cmdline())
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        haystack = f"{name} {cmdline}".lower()
        holders.append(
            PortHolder(
                port=port,
                label=wanted[port],
                pid=conn.pid,
                name=name,
                cmdline=cmdline,
                is_synapse=any(marker in haystack for marker in _SYNAPSE_CMDLINE_MARKERS),
            )
        )
    return sorted(holders, key=lambda h: h.port)


def port_is_serving(port: int, timeout: float = 2.0) -> bool:
    """Is whatever holds this port actually answering?

    Holding a port and *serving* on it are different things, and only the second
    means "working". A process that still owns 5173 but no longer responds is the
    stale-Vite case that blocked launches in 0.1.40; a Vite that answers is the
    renderer the user is currently using. Without this probe `doctor` cannot tell
    them apart and would invite `--fix` to kill a healthy dev server.
    """
    import socket

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
            sock.sendall(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
            sock.settimeout(timeout)
            return bool(sock.recv(1))
    except OSError:
        return False


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Local diagnostics. Designed to run when the daemon is down so
    the user can figure out *why*."""

    print(f"synapse-doctor — {__version__}")
    print(f"  python   : {sys.version.split()[0]}")
    print(f"  platform : {platform.system()} {platform.release()}")
    print(f"  daemon   : {daemon_base()}")
    token = discover_token()
    if token is None:
        print("  token    : (not found -- set SYNAPSE_TOKEN or run from data dir)")
    else:
        print(f"  token    : {token[:8]}... ({len(token)} chars)")
    daemon_ok = False
    try:
        health = request("GET", "/health", timeout=5.0)
        version = health.get("version", "?")
        daemon_ok = True
        print(f"  reach    : ok (daemon v{version})")
    except SynapseCliError as exc:
        print(f"  reach    : FAIL ({exc})")

    _report_ports(daemon_ok=daemon_ok, fix=bool(getattr(args, "fix", False)))
    return 0


def _report_ports(*, daemon_ok: bool, fix: bool) -> None:
    """Show who holds Synapse's ports, and optionally clear a genuine stray.

    `--fix` is deliberately narrow. It only ever terminates a holder that is
    recognisably ours AND cannot be the live daemon: if `/health` answered, the
    process on 7878 is the daemon that just replied, and killing it would break a
    working install to "repair" nothing. That is why the health probe runs first.
    """
    holders = find_port_holders()
    if not holders:
        ports = ", ".join(str(port) for port, _ in SYNAPSE_PORTS)
        print(f"  ports    : {ports} free (nothing listening)")
        return

    strays: list[PortHolder] = []
    for holder in holders:
        who = f"pid {holder.pid} · {holder.name}"
        # Serving == working. The daemon's own /health already answered this for
        # 7878; anything else gets a direct probe.
        serving = daemon_ok if holder.port == 7878 else port_is_serving(holder.port)
        if serving:
            owner = "the running daemon" if holder.port == 7878 else holder.label
            print(f"  port {holder.port} : in use by {owner} ({who}) -- responding")
            continue

        stale = holder.is_synapse
        tag = "Synapse-owned, NOT responding" if stale else "NOT Synapse -- left alone"
        print(f"  port {holder.port} : held by {who} [{tag}]")
        if holder.cmdline:
            print(f"             {holder.cmdline[:110]}")
        if stale:
            strays.append(holder)
        if not fix:
            continue
        if not stale:
            print("             skipped: --fix only clears Synapse-owned processes")
            continue
        try:
            import psutil

            proc = psutil.Process(holder.pid)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
            print(f"             cleared pid {holder.pid}")
        except Exception as exc:  # noqa: BLE001 -- diagnostics must not raise
            print(f"             could not clear pid {holder.pid}: {exc}")

    if strays and not fix:
        print("             (run `synapse doctor --fix` to clear the stale holder(s) above)")


# ── parser construction ───────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synapse",
        description="Synapse CLI — thin client over the daemon's /api/v1 surface.",
    )
    parser.add_argument("--version", action="version", version=f"synapse {__version__}")

    sub = parser.add_subparsers(dest="command", required=False)

    sub.add_parser("status", help="Show daemon health").set_defaults(func=_cmd_status)
    sub.add_parser("list", help="List managed projects").set_defaults(func=_cmd_list)

    p_start = sub.add_parser("start", help="Launch a project")
    p_start.add_argument("project_id")
    p_start.set_defaults(func=_cmd_start)

    p_stop = sub.add_parser("stop", help="Stop a project")
    p_stop.add_argument("project_id")
    p_stop.set_defaults(func=_cmd_stop)

    p_logs = sub.add_parser("logs", help="Show project logs")
    p_logs.add_argument("project_id")
    p_logs.add_argument("-f", "--follow", action="store_true", help="Stream live")
    p_logs.add_argument(
        "-n", "--lines", type=int, default=200, help="Lines to fetch (default 200)"
    )
    p_logs.add_argument(
        "--interval", type=float, default=2.0,
        help="Seconds between polls when following (default 2.0)",
    )
    p_logs.set_defaults(func=_cmd_logs)

    p_snap = sub.add_parser("snapshot", help="Export daemon state to JSON (Contract #28)")
    p_snap.add_argument("-o", "--output", default="synapse.snapshot.json")
    p_snap.set_defaults(func=_cmd_snapshot)

    p_rest = sub.add_parser("restore", help="Restore daemon state from JSON (Contract #28)")
    p_rest.add_argument("input")
    p_rest.set_defaults(func=_cmd_restore)

    p_doctor = sub.add_parser(
        "doctor",
        help="Local diagnostics (works without the daemon -- run this first when something is wrong)",
    )
    p_doctor.add_argument(
        "--fix",
        action="store_true",
        help="Clear Synapse-owned processes still holding 7878/5173 (never touches the live daemon)",
    )
    p_doctor.set_defaults(func=_cmd_doctor)

    return parser


# ── entrypoint ────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    func: Callable[[argparse.Namespace], int] | None = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 0
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
