"""Launch the Synapse live-monitor PowerShell loop without a console window.

Used by the current-user Scheduled Task. The wrapper stays alive for the
lifetime of the monitor so Task Scheduler still reports the task as Running.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    script = repo / "data" / "live-monitor" / "live-monitor.ps1"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=str(repo),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    return int(proc.wait())


if __name__ == "__main__":
    raise SystemExit(main())
