"""Launch scheduled background scripts without creating visible Windows consoles."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        return 64
    mode = sys.argv[1]
    if mode == 'powershell' and len(sys.argv) == 3:
        script = Path(sys.argv[2]).resolve(strict=True)
        cmd = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)]
    elif mode == 'cmd' and len(sys.argv) == 3:
        script = Path(sys.argv[2]).resolve(strict=True)
        cmd = ['cmd.exe', '/d', '/c', str(script)]
    else:
        return 64
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    result = subprocess.run(cmd, creationflags=flags, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())