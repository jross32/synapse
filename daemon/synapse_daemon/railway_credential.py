"""Read Railway token from environment or a Windows-user DPAPI-protected file.

The token is never returned to HTTP callers or written to application logs.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def read_railway_token(data_dir: Path) -> str:
    token = os.environ.get("RAILWAY_API_TOKEN", "").strip()
    if token:
        return token
    secret_path = data_dir / "railway-costs" / "railway-token.dpapi"
    if sys.platform != "win32" or not secret_path.is_file():
        return ""
    # Fixed PowerShell code, constant path passed as an argument (not interpolated).
    command = (
        "$ErrorActionPreference = 'Stop'; "
        "$s = Get-Content -LiteralPath $args[0] -Raw | ConvertTo-SecureString; "
        "$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s); "
        "try { [Console]::Out.Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)) } "
        "finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command, str(secret_path)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=8, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    # Do not log stdout: it contains the secret.
    return result.stdout.strip() if result.returncode == 0 else ""
