#!/usr/bin/env python
"""Run a direct CLI benchmark attempt and ingest the result into Synapse.

Example:
  python scripts/benchmark-direct-run.py ^
    --attempt-id abc123 ^
    --api-base http://127.0.0.1:7878 ^
    --token YOUR_TOKEN ^
    --output-dir .bench\abc123 ^
    -- python -V
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--api-base", default="http://127.0.0.1:7878")
    parser.add_argument("--token", required=True)
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("A command is required after '--'.")
    return args


def post_json(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Synapse-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Ingest failed: HTTP {exc.code} {body}") from exc
    return json.loads(raw) if raw else {}


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir or (Path.cwd() / "benchmark-direct" / args.attempt_id))
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at = utc_now_iso()
    proc = subprocess.run(
        args.command,
        cwd=args.cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    ended_at = utc_now_iso()
    elapsed = (
        datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)
    ).total_seconds()

    stdout_path = output_dir / "stdout.log"
    stderr_path = output_dir / "stderr.log"
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")

    payload = {
        "attempt_id": args.attempt_id,
        "status": "ingested" if proc.returncode == 0 else "failed",
        "exit_code": proc.returncode,
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_seconds": elapsed,
        "token_provenance": "unknown",
        "token_source": "unavailable",
        "verifier_summary": {
            "command": args.command,
            "cwd": args.cwd,
            "stdout_bytes": len((proc.stdout or "").encode("utf-8")),
            "stderr_bytes": len((proc.stderr or "").encode("utf-8")),
        },
        "metadata": {
            "ingested_via": "benchmark-direct-run.py",
            "command": args.command,
            "cwd": args.cwd,
        },
        "artifacts": [
            {
                "kind": "direct-cli-stdout",
                "label": "stdout",
                "path": str(stdout_path),
                "mime": "text/plain",
            },
            {
                "kind": "direct-cli-stderr",
                "label": "stderr",
                "path": str(stderr_path),
                "mime": "text/plain",
            },
        ],
    }

    attempt_json = output_dir / "attempt.json"
    attempt_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    result = post_json(
        f"{args.api_base.rstrip('/')}/api/v1/benchmarks/ingest-direct",
        args.token,
        payload,
    )
    print(json.dumps({"attempt_json": str(attempt_json), "ingest_result": result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
