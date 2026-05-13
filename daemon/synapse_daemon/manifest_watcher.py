"""Hot manifest reload (Contract #26).

Watches ``tools/`` and any registered project manifest paths. On file change
the daemon revalidates the manifest against its Pydantic schema; on success
it emits ``v1.manifest.reloaded``, on failure ``v1.manifest.error``.

This module is the skeleton: a thin wrapper around ``watchdog`` that the
daemon's startup wires together with the actual reload callbacks (Milestone B
+ G). Tests instantiate the watcher with a temp dir and synthetic events.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

ManifestChangeCallback = Callable[[Path], None]
ManifestErrorCallback = Callable[[Path, Exception], None]


class _ManifestHandler(FileSystemEventHandler):
    def __init__(self, on_change: ManifestChangeCallback, on_error: ManifestErrorCallback) -> None:
        super().__init__()
        self._on_change = on_change
        self._on_error = on_error

    def _dispatch(self, path_str: str) -> None:
        path = Path(path_str)
        if path.name != "manifest.json":
            return
        try:
            self._on_change(path)
        except Exception as exc:
            self._on_error(path, exc)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._dispatch(str(event.src_path))

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._dispatch(str(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._dispatch(str(event.dest_path))


class ManifestWatcher:
    """Watches one or more directories for manifest.json changes.

    Usage::

        watcher = ManifestWatcher(on_change=reload_manifest, on_error=record_failure)
        watcher.watch(Path("tools"))
        watcher.start()  # daemon startup
        ...
        watcher.stop()   # daemon shutdown
    """

    def __init__(
        self,
        on_change: ManifestChangeCallback,
        on_error: ManifestErrorCallback,
    ) -> None:
        self._on_change = on_change
        self._on_error = on_error
        self._observer: Any | None = None
        self._handler = _ManifestHandler(on_change, on_error)
        self._watched: list[Path] = []

    def watch(self, path: Path, *, recursive: bool = True) -> None:
        if self._observer is not None:
            raise RuntimeError("ManifestWatcher.watch() called after start()")
        if not path.exists():
            raise FileNotFoundError(path)
        self._watched.append(path)
        self._pending_recursive = recursive  # type: ignore[attr-defined]

    def start(self) -> None:
        if self._observer is not None:
            return
        self._observer = Observer()
        for path in self._watched:
            self._observer.schedule(self._handler, str(path), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=2.0)
        self._observer = None
