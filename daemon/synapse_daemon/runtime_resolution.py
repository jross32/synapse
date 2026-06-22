"""Resolve local AI/runtime binaries beyond a bare PATH lookup.

Synapse often runs as a desktop daemon, which means its environment can be
different from an interactive PowerShell session. On Windows in particular,
tools like Codex may exist on disk via a VS Code extension even when they are
not on PATH for the daemon process. This helper keeps runtime discovery and
launch resolution consistent across PTY spawn, probes, workbench defaults, and
profile readiness checks.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def resolve_command(command: str) -> str | None:
    """Return an executable path for ``command`` if one can be found."""

    normalized = (command or "").strip()
    if not normalized:
        return None

    direct = shutil.which(normalized)
    if direct:
        return direct

    if sys.platform != "win32":
        return None

    lowered = normalized.lower()
    home = Path.home()
    appdata = Path(os.getenv("APPDATA") or (home / "AppData" / "Roaming"))
    local_appdata = Path(os.getenv("LOCALAPPDATA") or (home / "AppData" / "Local"))
    program_files = Path(os.getenv("ProgramFiles") or r"C:\Program Files")
    system_root = Path(os.getenv("SystemRoot") or r"C:\Windows")

    candidates: list[Path] = []

    if lowered in {"claude", "claude.cmd", "claude.exe", "claude.ps1"}:
        candidates.extend(
            [
                appdata / "npm" / "claude.cmd",
                appdata / "npm" / "claude.exe",
                appdata / "npm" / "claude.ps1",
            ]
        )

    if lowered in {"codex", "codex.exe"}:
        for root in (home / ".vscode" / "extensions", home / ".vscode-insiders" / "extensions"):
            if not root.exists():
                continue
            for pattern in ("openai.chatgpt-*", "openai.openai-chatgpt-*"):
                candidates.extend(root.glob(f"{pattern}/bin/windows-*/codex.exe"))

    if lowered in {"copilot", "copilot.exe"}:
        candidates.extend(
            [
                local_appdata / "Microsoft" / "WinGet" / "Links" / "copilot.exe",
            ]
        )

    if lowered in {"gh", "gh.exe"}:
        candidates.extend(
            [
                local_appdata / "Microsoft" / "WinGet" / "Links" / "gh.exe",
            ]
        )

    if lowered in {"wsl", "wsl.exe"}:
        candidates.append(system_root / "System32" / "wsl.exe")

    if lowered in {"powershell", "powershell.exe"}:
        candidates.append(system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")

    if lowered in {"pwsh", "pwsh.exe"}:
        candidates.append(program_files / "PowerShell" / "7" / "pwsh.exe")

    if lowered in {"cmd", "cmd.exe"}:
        candidates.append(system_root / "System32" / "cmd.exe")

    if lowered in {"python", "python.exe", "python3", "python3.exe"}:
        candidates.append(Path(sys.executable))

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


__all__ = ["resolve_command"]
