"""ToolRegistry — the Synapse plugin system (Milestone F · v0.1.9).

A *tool* is a folder under ``tools/`` containing a ``manifest.json``. The
manifest is pure data — field definitions, action buttons, metadata. The
daemon **never imports code from a tool folder**.

Actions are run by *curated built-in handlers* compiled into the daemon
(:data:`_BUILTIN_HANDLER_FACTORIES`). This is the hybrid model: "drop a folder
in" plugin ergonomics with zero untrusted-code execution. A manifest whose id
has no compiled-in handler still appears in the UI — its actions are simply
inert (``runnable = False``).

Boot flow (called from the FastAPI lifespan):

  1. :meth:`load` scans ``tools/*/manifest.json``, validates each against
     :class:`~synapse_daemon.models.ToolManifest`, and binds a handler where
     one exists.
  2. The REST router (:mod:`routes_tools`) serves the manifests + state and
     dispatches actions to :meth:`run_action`.
  3. :meth:`shutdown_all` lets every handler release OS resources on exit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from .api_versions import event_name
from .errors import conflict, invalid, not_found
from .models import EntityStatus, ToolActionScope, ToolManifest, ToolState
from .storage import Storage
from .tools import ToolHandler
from .tools.cloudtap import CloudtapTool
from .tools.fast_money import FastMoneyTool
from .tools_primitives import is_known_primitive, run_primitive
from .ws import EventBus

if TYPE_CHECKING:
    from watchdog.observers.api import BaseObserver

log = logging.getLogger(__name__)

# Curated handler table. A manifest id maps to the handler class the daemon
# ships for it. Adding a built-in tool = drop a manifest folder + one entry
# here. Anything not in this table is listed read-only. Each class is
# constructed with ``(bus, storage)``.
_BUILTIN_HANDLER_FACTORIES: dict[str, type[ToolHandler]] = {
    "cloudtap": CloudtapTool,
    "fast-money": FastMoneyTool,
}


class ToolRegistry:
    """Loads tool manifests and dispatches their actions to handlers."""

    def __init__(self, tools_dir: Path, bus: EventBus, storage: Storage | None = None) -> None:
        self._tools_dir = tools_dir
        self._bus = bus
        self._storage = storage
        self._manifests: dict[str, ToolManifest] = {}
        self._handlers: dict[str, ToolHandler] = {}
        # Hot-reload plumbing (v0.1.21).
        self._observer: BaseObserver | None = None
        self._watch_loop: asyncio.AbstractEventLoop | None = None
        self._reload_lock = threading.Lock()
        self._reload_scheduled = False

    # ── loading ──────────────────────────────────────────────────────────

    def load(self) -> list[str]:
        """Scan the tools directory; return the ids successfully loaded.

        Safe to call once at boot. A malformed manifest is logged and skipped
        — one bad tool never blocks the rest.
        """

        self._manifests.clear()
        self._handlers.clear()

        if not self._tools_dir.exists():
            log.info("Tools directory %s does not exist; no tools loaded.", self._tools_dir)
            return []

        for manifest_path in sorted(self._tools_dir.glob("*/manifest.json")):
            manifest = self._read_manifest(manifest_path)
            if manifest is None:
                continue
            if manifest.id in self._manifests:
                log.warning("Duplicate tool id '%s' at %s; skipping.", manifest.id, manifest_path)
                continue

            factory = _BUILTIN_HANDLER_FACTORIES.get(manifest.id)
            has_primitives = any(a.primitive for a in manifest.actions)
            if factory is not None:
                manifest.runnable = True
                self._handlers[manifest.id] = factory(self._bus, self._storage)
            elif has_primitives:
                # Declarative tier (v0.1.22) -- runnable without a handler.
                manifest.runnable = True
            else:
                manifest.runnable = False
                log.info(
                    "Tool '%s' has no built-in handler or primitives; listing it read-only.",
                    manifest.id,
                )

            self._manifests[manifest.id] = manifest

        loaded = sorted(self._manifests)
        log.info("ToolRegistry loaded %d tool(s): %s", len(loaded), loaded)
        return loaded

    def _read_manifest(self, path: Path) -> ToolManifest | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Skipping unreadable tool manifest %s: %s", path, exc)
            return None
        try:
            return ToolManifest.model_validate(raw)
        except Exception as exc:  # pydantic ValidationError + anything else
            log.warning("Skipping invalid tool manifest %s: %s", path, exc)
            return None

    # ── queries ──────────────────────────────────────────────────────────

    def list_manifests(self) -> list[ToolManifest]:
        return [self._manifests[i] for i in sorted(self._manifests)]

    def get_manifest(self, tool_id: str) -> ToolManifest:
        manifest = self._manifests.get(tool_id)
        if manifest is None:
            raise not_found("tool", tool_id)
        return manifest

    def get_state(self, tool_id: str) -> ToolState:
        # Validates existence first (404 with a proper envelope).
        self.get_manifest(tool_id)
        handler = self._handlers.get(tool_id)
        if handler is None:
            return ToolState(tool_id=tool_id, status=EntityStatus.IDLE)
        return handler.state()

    # ── actions ──────────────────────────────────────────────────────────

    async def run_action(
        self,
        tool_id: str,
        action_id: str,
        fields: dict,
        item_id: str | None = None,
    ) -> ToolState:
        manifest = self.get_manifest(tool_id)

        action = next((a for a in manifest.actions if a.id == action_id), None)
        if action is None:
            raise invalid("tool", f"Tool '{tool_id}' has no action '{action_id}'.")

        # Declarative tier (v0.1.22): the manifest invokes a vetted primitive
        # directly; no Python handler involved. Item scope doesn't apply --
        # primitives are stateless one-shots, so any item_id is ignored.
        if action.primitive:
            if not is_known_primitive(action.primitive):
                raise invalid(
                    "tool",
                    f"Action '{action_id}' invokes unknown primitive '{action.primitive}'.",
                )
            return await run_primitive(
                action.primitive, action.params or {}, fields or {}, self._bus, tool_id
            )

        # An item-scoped action (e.g. "close this tunnel") needs a target.
        if action.scope == ToolActionScope.ITEM and not item_id:
            raise invalid(
                "tool",
                f"Action '{action_id}' is item-scoped and requires an item id.",
            )

        handler = self._handlers.get(tool_id)
        if handler is None:
            raise conflict(
                "tool",
                f"Tool '{tool_id}' has no executable handler in this build.",
            )

        return await handler.run_action(action_id, fields or {}, item_id)

    # ── hot reload (v0.1.21 · ADR-0001 step 1) ───────────────────────────

    async def reload(self) -> dict[str, list[str]]:
        """Re-scan ``tools/`` in place. Preserves live handler state for any
        tool whose id is still present.

        Returns ``{"added": [...], "removed": [...], "kept": [...]}`` so
        callers can log meaningful diffs. Publishes ``v1.tool.reloaded`` on
        the bus so the renderer's Tools page refetches automatically.
        """

        old_ids = set(self._manifests.keys())
        new_manifests: dict[str, ToolManifest] = {}

        if self._tools_dir.exists():
            for manifest_path in sorted(self._tools_dir.glob("*/manifest.json")):
                manifest = self._read_manifest(manifest_path)
                if manifest is None or manifest.id in new_manifests:
                    continue
                if manifest.id in _BUILTIN_HANDLER_FACTORIES or any(
                    a.primitive for a in manifest.actions
                ):
                    manifest.runnable = True
                new_manifests[manifest.id] = manifest

        new_ids = set(new_manifests)
        added = sorted(new_ids - old_ids)
        removed = sorted(old_ids - new_ids)
        kept = sorted(old_ids & new_ids)

        for tool_id in removed:
            handler = self._handlers.pop(tool_id, None)
            if handler is not None:
                try:
                    await handler.shutdown()
                except Exception:  # pragma: no cover — defensive
                    log.exception("Tool '%s' raised during reload shutdown.", tool_id)

        for tool_id in added:
            factory = _BUILTIN_HANDLER_FACTORIES.get(tool_id)
            if factory is not None:
                self._handlers[tool_id] = factory(self._bus, self._storage)

        # Swap manifests last so any concurrent reader sees a coherent state.
        self._manifests = new_manifests

        log.info(
            "ToolRegistry reload: +%d added, -%d removed, %d kept",
            len(added),
            len(removed),
            len(kept),
        )
        await self._bus.publish(
            event_name("tool", "reloaded"),
            {
                "loaded": sorted(new_ids),
                "added": added,
                "removed": removed,
                "kept": kept,
            },
        )
        return {"added": added, "removed": removed, "kept": kept}

    def start_watching(self, loop: asyncio.AbstractEventLoop) -> None:
        """Begin watching ``tools/`` for manifest changes. Idempotent."""

        if self._observer is not None:
            return
        if not self._tools_dir.exists():
            log.info("Tools dir %s missing; hot reload not started.", self._tools_dir)
            return
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:  # pragma: no cover — watchdog is in dev deps
            log.warning("watchdog not installed; hot tool reload disabled.")
            return

        registry = self

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event) -> None:  # type: ignore[override]
                src = getattr(event, "src_path", "") or ""
                dst = getattr(event, "dest_path", "") or ""
                # Filter to manifest.json files + directory create/delete --
                # ignores transient editor side-files (e.g. .swp).
                if (
                    src.endswith("manifest.json")
                    or dst.endswith("manifest.json")
                    or event.is_directory
                ):
                    registry._schedule_reload()

        observer = Observer()
        observer.schedule(_Handler(), str(self._tools_dir), recursive=True)
        observer.start()
        self._observer = observer
        self._watch_loop = loop
        log.info("Watching %s for tool manifest changes.", self._tools_dir)

    def stop_watching(self) -> None:
        """Stop the watcher. Idempotent."""

        observer = self._observer
        if observer is None:
            return
        self._observer = None
        try:
            observer.stop()
            observer.join(timeout=2)
        except Exception:  # pragma: no cover — defensive
            log.exception("Error stopping tools-dir observer.")

    def _schedule_reload(self) -> None:
        """Coalesce a flurry of file events into one reload (250 ms debounce)."""

        with self._reload_lock:
            if self._reload_scheduled:
                return
            self._reload_scheduled = True

        loop = self._watch_loop
        if loop is None:
            return

        registry = self

        async def _coalesced() -> None:
            try:
                await asyncio.sleep(0.25)
            finally:
                with registry._reload_lock:
                    registry._reload_scheduled = False
            try:
                await registry.reload()
            except Exception:  # pragma: no cover — defensive
                log.exception("Hot reload failed.")

        asyncio.run_coroutine_threadsafe(_coalesced(), loop)

    # ── lifecycle ────────────────────────────────────────────────────────

    async def shutdown_all(self) -> None:
        self.stop_watching()
        for tool_id, handler in self._handlers.items():
            try:
                await handler.shutdown()
            except Exception:  # pragma: no cover — defensive
                log.exception("Tool '%s' raised during shutdown.", tool_id)
