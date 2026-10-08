"""Persistent metadata for asynchronous command jobs.

Metadata is written atomically so the command-result endpoint can recover
completed results after daemon restart. No command text is logged here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


def job_root(data_dir: str | Path) -> Path:
    return Path(data_dir) / "command-jobs"


def save_job(data_dir: str | Path, job_id: str, payload: dict[str, Any]) -> None:
    root = job_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / (job_id + ".json")
    handle, temporary = tempfile.mkstemp(prefix=job_id + ".", suffix=".tmp", dir=root)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_job(data_dir: str | Path, job_id: str) -> dict[str, Any] | None:
    if not job_id or not all(c in "0123456789abcdef" for c in job_id):
        return None
    path = job_root(data_dir) / (job_id + ".json")
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
