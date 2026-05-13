"""Per-process log capture (Contract #3).

Every spawned child process has its stdout + stderr teed to a rotating log
file. Tile UI shows "View logs" → opens latest file. "Live tail" mode streams
appends over WebSocket.

This module defines the file layout + rotation policy. The actual spawn-and-tee
plumbing lands in :mod:`synapse_daemon.process_manager` (Milestone E).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Final

# Rotation policy — Contract #3.
ROTATION_MAX_BYTES: Final[int] = 10 * 1024 * 1024   # 10 MB per file
ROTATION_BACKUP_COUNT: Final[int] = 5               # keep 5 historical files
LOG_FILENAME_FORMAT: Final[str] = "%Y-%m-%dT%H-%M-%S"


def log_root(data_dir: Path) -> Path:
    """Root folder for all per-process logs."""

    return data_dir / "logs"


def entity_log_dir(data_dir: Path, entity_id: str) -> Path:
    """Folder for a single entity's logs. Created on demand.

    Path: ``<data>/logs/<entity-id>/`` — kebab-case enforced by Contract #10
    upstream; this function trusts its caller.
    """

    path = log_root(data_dir) / entity_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_log_path(data_dir: Path, entity_id: str, now: datetime | None = None) -> Path:
    """Return a fresh log filename for a new spawn.

    Format: ``<data>/logs/<entity-id>/<ISO-timestamp>.log``.
    """

    ts = (now or datetime.now(timezone.utc)).strftime(LOG_FILENAME_FORMAT)
    return entity_log_dir(data_dir, entity_id) / f"{ts}.log"


def list_logs(data_dir: Path, entity_id: str) -> list[Path]:
    """All log files for an entity, newest first. Empty list if none."""

    folder = log_root(data_dir) / entity_id
    if not folder.exists():
        return []
    return sorted(folder.glob("*.log"), reverse=True)


def latest_log(data_dir: Path, entity_id: str) -> Path | None:
    """Most recent log file for an entity, or ``None``."""

    logs = list_logs(data_dir, entity_id)
    return logs[0] if logs else None
