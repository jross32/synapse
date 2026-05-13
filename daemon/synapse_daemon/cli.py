"""Synapse CLI (Contract #27).

A thin client over the daemon's REST API. Same commands, same data, same
audit log — no direct DB access. Commands map 1-to-1 with REST endpoints
defined in ``docs/api-changes.md``.

This module ships in v0.1.2 with command parsing + help text only; HTTP
plumbing lives in :mod:`synapse_daemon.cli_http` (Milestone B) once a daemon
is actually reachable.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Callable

from . import __version__


# ── command handlers (placeholders for v0.1.2) ────────────────────────────


def _cmd_status(args: argparse.Namespace) -> int:
    print(f"synapse {__version__} — daemon HTTP client not wired yet (Milestone B).")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    print("synapse list — will GET /api/v1/projects when daemon is wired.")
    return 0


def _cmd_start(args: argparse.Namespace) -> int:
    print(f"synapse start {args.project_id} — will POST /api/v1/projects/{args.project_id}/launch.")
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    print(f"synapse stop {args.project_id} — will POST /api/v1/projects/{args.project_id}/stop.")
    return 0


def _cmd_logs(args: argparse.Namespace) -> int:
    follow = " (follow)" if args.follow else ""
    print(f"synapse logs {args.project_id}{follow} — will GET /api/v1/projects/{args.project_id}/logs.")
    return 0


def _cmd_snapshot(args: argparse.Namespace) -> int:
    print(f"synapse snapshot → {args.output} — will POST /api/v1/snapshot.")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    print(f"synapse restore {args.input} — will POST /api/v1/restore.")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Local diagnostics — runs without the daemon."""

    import platform

    print(f"synapse-doctor — {__version__}")
    print(f"  python   : {sys.version.split()[0]}")
    print(f"  platform : {platform.system()} {platform.release()}")
    print("  daemon   : (probe lands in Milestone B)")
    print("  config   : (probe lands in Milestone B)")
    return 0


# ── parser construction ───────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synapse",
        description="Synapse CLI — thin client over the daemon's /api/v1 surface.",
    )
    parser.add_argument("--version", action="version", version=f"synapse {__version__}")

    sub = parser.add_subparsers(dest="command", required=False)

    sub.add_parser("status", help="Show daemon + project status").set_defaults(func=_cmd_status)
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
    p_logs.set_defaults(func=_cmd_logs)

    p_snap = sub.add_parser("snapshot", help="Export daemon state to JSON (Contract #28)")
    p_snap.add_argument("-o", "--output", default="synapse.snapshot.json")
    p_snap.set_defaults(func=_cmd_snapshot)

    p_rest = sub.add_parser("restore", help="Restore daemon state from JSON (Contract #28)")
    p_rest.add_argument("input")
    p_rest.set_defaults(func=_cmd_restore)

    sub.add_parser("doctor", help="Local diagnostics (no daemon required)").set_defaults(
        func=_cmd_doctor
    )

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
