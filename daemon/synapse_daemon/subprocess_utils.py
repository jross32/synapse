"""Small cross-platform helpers for background subprocesses.

Synapse is normally launched headlessly on Windows. A console-subsystem child
created without CREATE_NO_WINDOW can cause Windows Terminal/OpenConsole to
materialize a visible window even when its parent has no console. Keep all
background helpers explicitly console-less.
"""

from __future__ import annotations

import os
import subprocess


def headless_creationflags(extra: int = 0) -> int:
    """Return process creation flags suitable for background children."""
    if os.name != "nt":
        return 0
    return int(extra) | int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
