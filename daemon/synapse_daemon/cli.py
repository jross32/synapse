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
from typing import Callable

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


def _cmd_doctor(_args: argparse.Namespace) -> int:
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
    try:
        health = request("GET", "/health", timeout=5.0)
        version = health.get("version", "?")
        print(f"  reach    : ok (daemon v{version})")
    except SynapseCliError as exc:
        print(f"  reach    : FAIL ({exc})")
    return 0


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

    sub.add_parser(
        "doctor",
        help="Local diagnostics (works without the daemon -- run this first when something is wrong)",
    ).set_defaults(func=_cmd_doctor)

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
