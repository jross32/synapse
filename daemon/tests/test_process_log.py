"""Contract #3 — per-process log layout."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from synapse_daemon.process_log import (
    LOG_FILENAME_FORMAT,
    ROTATION_BACKUP_COUNT,
    ROTATION_MAX_BYTES,
    entity_log_dir,
    latest_log,
    list_logs,
    new_log_path,
)


def test_rotation_constants_match_contract() -> None:
    # Contract #3: 10 MB × 5 files.
    assert ROTATION_MAX_BYTES == 10 * 1024 * 1024
    assert ROTATION_BACKUP_COUNT == 5


def test_log_dir_is_created_on_demand(tmp_path: Path) -> None:
    d = entity_log_dir(tmp_path, "wbscrper")
    assert d.exists()
    assert d.is_dir()
    assert d.parent.name == "logs"
    assert d.name == "wbscrper"


def test_new_log_path_uses_iso_timestamp(tmp_path: Path) -> None:
    now = datetime(2026, 5, 13, 14, 22, 5, tzinfo=timezone.utc)
    p = new_log_path(tmp_path, "wbscrper", now=now)
    assert p.name == now.strftime(LOG_FILENAME_FORMAT) + ".log"
    assert p.parent == tmp_path / "logs" / "wbscrper"


def test_list_and_latest_logs(tmp_path: Path) -> None:
    assert list_logs(tmp_path, "missing") == []
    assert latest_log(tmp_path, "missing") is None

    for i, t in enumerate(["2026-05-13T10-00-00", "2026-05-13T11-00-00", "2026-05-13T09-00-00"]):
        f = entity_log_dir(tmp_path, "wbscrper") / f"{t}.log"
        f.write_text(f"line {i}\n", encoding="utf-8")

    logs = list_logs(tmp_path, "wbscrper")
    assert [p.stem for p in logs] == [
        "2026-05-13T11-00-00",
        "2026-05-13T10-00-00",
        "2026-05-13T09-00-00",
    ]
    latest = latest_log(tmp_path, "wbscrper")
    assert latest is not None
    assert latest.stem == "2026-05-13T11-00-00"
