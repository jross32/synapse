"""End-to-end regression tests for scripts/coordination-preflight.ps1."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "coordination-preflight.ps1"


class _OverlapHandler(BaseHTTPRequestHandler):
    server: "_OverlapServer"

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.seen_path = self.path
        self.server.seen_token = self.headers.get("X-Synapse-Token")
        self.server.seen_body = json.loads(raw.decode("utf-8")) if raw else {}
        payload = json.dumps({"has_conflicts": False, "conflicts": []}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class _OverlapServer(ThreadingHTTPServer):
    seen_path: str | None = None
    seen_token: str | None = None
    seen_body: dict[str, Any] | None = None


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 is required")
def test_documented_staged_preflight_uses_trusted_local_token_file(tmp_path: Path) -> None:
    """The normal -Staged invocation must authenticate instead of silently degrading."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "data").mkdir()
    shutil.copy2(SCRIPT, repo / "scripts" / SCRIPT.name)
    (repo / "data" / "auth-token").write_text("local-test-token\n", encoding="utf-8")
    (repo / "tracked.txt").write_text("staged\n", encoding="utf-8")
    _git(repo, "init")
    _git(repo, "add", "tracked.txt")

    server = _OverlapServer(("127.0.0.1", 0), _OverlapHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = os.environ.copy()
        env.pop("SYNAPSE_LOCAL_TOKEN", None)
        env.pop("SYNAPSE_SESSION_ID", None)
        result = subprocess.run(
            [
                shutil.which("pwsh") or "pwsh",
                "-NoProfile",
                "-File",
                str(repo / "scripts" / SCRIPT.name),
                "-Staged",
                "-Port",
                str(server.server_port),
            ],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.returncode == 0, result.stdout + result.stderr
    assert server.seen_path == "/api/v1/coordination/overlap"
    assert server.seen_token == "local-test-token"
    assert server.seen_body is not None
    assert server.seen_body["paths"] == ["tracked.txt"]
    assert "No lane conflicts on staged files." in result.stdout
    assert "Coordination endpoint unavailable" not in result.stdout
    assert "local-test-token" not in result.stdout + result.stderr
