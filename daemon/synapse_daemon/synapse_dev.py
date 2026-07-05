"""Gated developer-loop helpers for Synapse self-improvement (ADR-0007 slice 1)."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .runtime_paths import repo_root
from .time_utils import to_iso, utc_now

_ENABLE_ENV = "SYNAPSE_DEV_ENABLED"
_TAIL_LIMIT = 8 * 1024


def _tail_text(text: str, *, limit: int = _TAIL_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _command_result(command: list[str], *, cwd: Path, log_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        duration = time.perf_counter() - started
        payload = {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "combined": str(exc),
            "duration_s": round(duration, 3),
            "log_path": str(log_path),
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(str(exc), encoding="utf-8")
        return payload
    duration = time.perf_counter() - started
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(combined, encoding="utf-8")
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "combined": combined,
        "duration_s": round(duration, 3),
        "log_path": str(log_path),
    }


def _parse_pytest(payload: dict[str, Any]) -> dict[str, Any]:
    combined = str(payload.get("combined") or "")
    counts = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
    }
    for key in counts:
        match = re.search(rf"(\d+)\s+{key}", combined)
        if match:
            counts[key] = int(match.group(1))
    return {
        **counts,
        "duration_s": payload["duration_s"],
        "tail": _tail_text(combined),
        "ok": bool(payload["ok"]),
        "log_path": payload["log_path"],
    }


def _parse_tsc(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    combined = "\n".join(str(item.get("combined") or "") for item in payloads if item.get("combined"))
    errors: list[str] = []
    for line in combined.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if "error ts" in lowered or lowered.startswith("error"):
            errors.append(stripped)
    return {
        "ok": all(bool(item["ok"]) for item in payloads),
        "duration_s": round(sum(float(item["duration_s"]) for item in payloads), 3),
        "errors": errors[:25],
        "tail": _tail_text(combined),
        "log_paths": [item["log_path"] for item in payloads],
    }


class SynapseDevManager:
    def __init__(self, data_dir: Path, *, target_repo: Path | None = None) -> None:
        self._data_dir = Path(data_dir)
        self._repo_root = target_repo or repo_root()
        self._last_test_report: dict[str, Any] | None = None

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    def enabled(self) -> bool:
        return os.environ.get(_ENABLE_ENV) == "1"

    def require_enabled_message(self) -> dict[str, Any]:
        return {
            "env_var": _ENABLE_ENV,
            "required_value": "1",
            "message": "Set SYNAPSE_DEV_ENABLED=1 to allow AI-driven developer actions.",
        }

    def _log_dir(self) -> Path:
        return self._data_dir / "synapse-dev"

    def resolve_test_path(self, path: str) -> Path:
        raw = Path(path)
        candidate = raw if raw.is_absolute() else (self._repo_root / raw)
        resolved = candidate.resolve()
        tests_root = (self._repo_root / "daemon" / "tests").resolve()
        try:
            resolved.relative_to(tests_root)
        except ValueError as exc:
            raise ValueError("path must resolve under daemon/tests/") from exc
        if resolved.suffix != ".py":
            raise ValueError("path must point to a Python test file under daemon/tests/.")
        return resolved

    async def run_full_tests(
        self,
        *,
        python_args: list[str] | None = None,
        tsc_args: list[str] | None = None,
    ) -> dict[str, Any]:
        run_id = f"full-{utc_now().strftime('%Y%m%d%H%M%S')}"
        pytest_log = self._log_dir() / f"{run_id}-pytest.log"
        renderer_tsc_log = self._log_dir() / f"{run_id}-tsc-renderer.log"
        electron_tsc_log = self._log_dir() / f"{run_id}-tsc-electron.log"
        python_command = [sys.executable, "-m", "pytest", *list(python_args or [])]
        tsc_tail = list(tsc_args or [])
        pytest_payload, renderer_tsc_payload, electron_tsc_payload = await asyncio.gather(
            asyncio.to_thread(
                _command_result,
                python_command,
                cwd=self._repo_root / "daemon",
                log_path=pytest_log,
            ),
            asyncio.to_thread(
                _command_result,
                ["npx", "tsc", "--noEmit", "-p", "tsconfig.json", *tsc_tail],
                cwd=self._repo_root,
                log_path=renderer_tsc_log,
            ),
            asyncio.to_thread(
                _command_result,
                ["npx", "tsc", "--noEmit", "-p", "electron/tsconfig.json", *tsc_tail],
                cwd=self._repo_root,
                log_path=electron_tsc_log,
            ),
        )
        report = {
            "ok": bool(pytest_payload["ok"]) and bool(renderer_tsc_payload["ok"]) and bool(electron_tsc_payload["ok"]),
            "ran_at": to_iso(utc_now()),
            "mode": "full",
            "pytest": _parse_pytest(pytest_payload),
            "tsc": _parse_tsc([renderer_tsc_payload, electron_tsc_payload]),
        }
        self._last_test_report = report
        return report

    async def run_file_test(
        self,
        path: str,
        *,
        python_args: list[str] | None = None,
    ) -> dict[str, Any]:
        test_path = self.resolve_test_path(path)
        run_id = f"file-{utc_now().strftime('%Y%m%d%H%M%S')}"
        pytest_log = self._log_dir() / f"{run_id}-pytest.log"
        relative = test_path.relative_to(self._repo_root)
        pytest_payload = await asyncio.to_thread(
            _command_result,
            [sys.executable, "-m", "pytest", str(relative), *list(python_args or [])],
            cwd=self._repo_root,
            log_path=pytest_log,
        )
        report = {
            "ok": bool(pytest_payload["ok"]),
            "ran_at": to_iso(utc_now()),
            "mode": "file",
            "path": str(relative).replace("\\", "/"),
            "pytest": _parse_pytest(pytest_payload),
        }
        self._last_test_report = report
        return report

    def tests_summary(self) -> dict[str, Any]:
        if self._last_test_report is None:
            return {
                "last_run_ok": None,
                "last_run_at": None,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "mode": None,
            }
        pytest_block = self._last_test_report.get("pytest", {})
        return {
            "last_run_ok": self._last_test_report.get("ok"),
            "last_run_at": self._last_test_report.get("ran_at"),
            "passed": int(pytest_block.get("passed") or 0),
            "failed": int(pytest_block.get("failed") or 0),
            "skipped": int(pytest_block.get("skipped") or 0),
            "mode": self._last_test_report.get("mode"),
        }

    def git_summary(self) -> dict[str, Any]:
        branch = ""
        head = ""
        ahead: int | None = None
        behind: int | None = None
        try:
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self._repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            ).stdout.strip()
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self._repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            ).stdout.strip()
            upstream = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "@{upstream}"],
                cwd=str(self._repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if upstream.returncode == 0 and upstream.stdout.strip():
                counts = subprocess.run(
                    ["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                    cwd=str(self._repo_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                ).stdout.strip()
                parts = counts.split()
                if len(parts) == 2:
                    ahead = int(parts[0])
                    behind = int(parts[1])
        except OSError:
            pass
        return {
            "branch": branch or "unknown",
            "head": head or "",
            "ahead": ahead,
            "behind": behind,
            "repo_path": str(self._repo_root),
            "synapse_dev_enabled": self.enabled(),
        }
