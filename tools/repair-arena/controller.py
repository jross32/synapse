from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parents[1]
DAEMON_DIR = REPO_ROOT / "daemon"
if str(DAEMON_DIR) not in sys.path:
    sys.path.insert(0, str(DAEMON_DIR))

from synapse_daemon.repair_arena import readiness, run_repair_arena  # noqa: E402
from synapse_daemon.repair_arena_candidates import evaluate_staged_candidate  # noqa: E402


def _auth_token() -> str:
    token_path = REPO_ROOT / "data" / "auth-token"
    if not token_path.is_file():
        raise RuntimeError("Synapse auth token is unavailable")
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("Synapse auth token is empty")
    return token


def resolve_project(project_id: str) -> dict:
    project_id = str(project_id or "").strip()
    if not project_id:
        raise ValueError("project id is required")
    req = Request(
        "http://127.0.0.1:7878/api/v1/projects",
        method="GET",
        headers={"Accept": "application/json", "X-Synapse-Token": _auth_token()},
    )
    try:
        with urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Synapse project lookup failed with HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Synapse project lookup is unavailable") from exc

    rows = payload if isinstance(payload, list) else payload.get("projects", [])
    needle = project_id.casefold()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("id") or "").casefold() == needle or str(row.get("name") or "").casefold() == needle:
            if not row.get("path"):
                raise RuntimeError("Registered project has no path")
            return row
    raise ValueError(f"Synapse project '{project_id}' was not found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Synapse Repair Arena")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Check App Doctor + Agent Arcade readiness")
    run = sub.add_parser("run", help="Run a planning-only repair tournament")
    run.add_argument("--project", required=True, help="Registered Synapse project id or exact name")
    run.add_argument("--rounds", type=int, default=2, choices=[1, 2, 3])
    run.add_argument("--mode", choices=["demo", "gemini"], default="demo")

    stage = sub.add_parser("stage", help="Run the tournament and prepare isolated candidate worktrees")
    stage.add_argument("--project", required=True, help="Registered Synapse project id or exact name")
    stage.add_argument("--rounds", type=int, default=2, choices=[1, 2, 3])
    stage.add_argument("--mode", choices=["demo", "gemini"], default="demo")
    stage.add_argument("--candidate-count", type=int, default=3, choices=[1, 2, 3])

    evaluate = sub.add_parser("evaluate", help="Read-only evaluation of one staged candidate")
    evaluate.add_argument("--project", required=True, help="Registered Synapse project id or exact name")
    evaluate.add_argument("--tournament", required=True, help="Repair Arena tournament/staging id")
    evaluate.add_argument("--candidate", default="", help="Candidate agent id/name or numeric rank; defaults to rank 1")

    args = parser.parse_args()
    try:
        if args.command == "check":
            result = readiness()
        elif args.command == "evaluate":
            project = resolve_project(args.project)
            candidate_raw = str(args.candidate or "").strip()
            candidate = int(candidate_raw) if candidate_raw.isdigit() else (candidate_raw or None)
            result = evaluate_staged_candidate(
                str(project.get("id") or ""),
                args.tournament,
                candidate=candidate,
            )
        else:
            project = resolve_project(args.project)
            result = run_repair_arena(
                str(project["path"]),
                project_id=str(project.get("id") or ""),
                project_name=str(project.get("name") or ""),
                rounds=args.rounds,
                mode=args.mode,
                persist=True,
                prepare_candidates=args.command == "stage",
                candidate_count=getattr(args, "candidate_count", 3),
            )
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "error_type": type(exc).__name__}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
