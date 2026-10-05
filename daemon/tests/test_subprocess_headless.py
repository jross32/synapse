from __future__ import annotations

import ast
from pathlib import Path

from synapse_daemon import subprocess_utils


BACKGROUND_MODULES = (
    "coder_runtimes.py",
    "coordination.py",
    "git_worktrees.py",
    "health.py",
    "local_agent.py",
    "local_bench.py",
    "local_models.py",
    "local_pipeline.py",
    "mcp_connector.py",
    "mcp_servers.py",
    "profile.py",
    "project_doctor.py",
    "repo_watch.py",
    "routes_review.py",
    "synapse_dev.py",
)


def test_headless_creationflags_adds_create_no_window_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(subprocess_utils.os, "name", "nt")
    monkeypatch.setattr(
        subprocess_utils.subprocess,
        "CREATE_NO_WINDOW",
        0x08000000,
        raising=False,
    )

    assert subprocess_utils.headless_creationflags() == 0x08000000
    assert subprocess_utils.headless_creationflags(0x200) == 0x08000200


def test_headless_creationflags_is_zero_on_non_windows(monkeypatch) -> None:
    monkeypatch.setattr(subprocess_utils.os, "name", "posix")
    assert subprocess_utils.headless_creationflags(0x200) == 0


def test_background_subprocess_calls_explicitly_disable_windows_console() -> None:
    root = Path(__file__).parents[1] / "synapse_daemon"
    missing: list[str] = []

    for name in BACKGROUND_MODULES:
        path = root / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
                and func.attr in {"run", "Popen"}
            ):
                continue
            if not any(keyword.arg == "creationflags" for keyword in node.keywords):
                missing.append(f"{name}:{node.lineno}:{func.attr}")

    assert missing == [], "background subprocesses missing creationflags: " + ", ".join(missing)
