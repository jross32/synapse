"""Contract #26 — hot manifest reload watcher."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from synapse_daemon.manifest_watcher import ManifestWatcher


def _wait_for(predicate, timeout=2.0, interval=0.05):
    """Spin until predicate() is true or timeout expires."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_watcher_picks_up_manifest_changes(tmp_path: Path) -> None:
    tool_dir = tmp_path / "tools" / "cloudtap"
    tool_dir.mkdir(parents=True)
    manifest = tool_dir / "manifest.json"
    manifest.write_text('{"id":"cloudtap","name":"Cloudtap"}', encoding="utf-8")

    changes: list[Path] = []
    errors: list[tuple[Path, Exception]] = []

    watcher = ManifestWatcher(
        on_change=lambda p: changes.append(p),
        on_error=lambda p, e: errors.append((p, e)),
    )
    watcher.watch(tmp_path / "tools")
    watcher.start()
    try:
        manifest.write_text('{"id":"cloudtap","name":"Cloudtap v2"}', encoding="utf-8")
        assert _wait_for(lambda: any(p.name == "manifest.json" for p in changes))
    finally:
        watcher.stop()

    assert not errors


def test_watcher_ignores_non_manifest_files(tmp_path: Path) -> None:
    tool_dir = tmp_path / "tools" / "cloudtap"
    tool_dir.mkdir(parents=True)

    changes: list[Path] = []
    watcher = ManifestWatcher(
        on_change=lambda p: changes.append(p),
        on_error=lambda p, e: None,
    )
    watcher.watch(tmp_path / "tools")
    watcher.start()
    try:
        (tool_dir / "README.md").write_text("hi", encoding="utf-8")
        time.sleep(0.2)
    finally:
        watcher.stop()

    assert changes == []


def test_watch_after_start_raises(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    w = ManifestWatcher(on_change=lambda p: None, on_error=lambda p, e: None)
    w.watch(tmp_path)
    w.start()
    try:
        with pytest.raises(RuntimeError):
            w.watch(tmp_path)
    finally:
        w.stop()
