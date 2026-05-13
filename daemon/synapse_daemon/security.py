"""Security guards (Contracts #15, #16).

This module's only job today is to refuse to run with elevated privileges
unless the user explicitly opts in. See ``docs/security.md``.

Contract #15 (no telemetry by default) is enforced by simply not making any
outbound calls from the daemon. There is no opt-in flag yet — adding one
requires an ADR.
"""

from __future__ import annotations

import ctypes
import os
import sys


def is_admin() -> bool:
    """Return True if the current process is running with admin/root rights."""

    if sys.platform == "win32":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except Exception:
            return False
    return os.geteuid() == 0  # type: ignore[attr-defined]


def assert_not_admin(*, allow_admin: bool = False) -> None:
    """Exit with a clear error if running as admin without ``--allow-admin``.

    Synapse refuses by default because managed child processes inherit token
    elevation, which is rarely what a user wants and frequently dangerous.
    """

    if not is_admin():
        return
    if allow_admin:
        return

    sys.stderr.write(
        "Synapse refuses to run as Administrator/root.\n"
        "Re-launch without elevation, or pass --allow-admin if you are sure.\n"
        "See docs/security.md for rationale.\n"
    )
    raise SystemExit(2)
