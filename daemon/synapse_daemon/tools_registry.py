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

import json
import logging
from pathlib import Path

from .errors import conflict, invalid, not_found
from .models import EntityStatus, ToolActionScope, ToolManifest, ToolState
from .storage import Storage
from .tools import ToolHandler
from .tools.cloudtap import CloudtapTool
from .ws import EventBus

log = logging.getLogger(__name__)

# Curated handler table. A manifest id maps to the handler class the daemon
# ships for it. Adding a built-in tool = drop a manifest folder + one entry
# here. Anything not in this table is listed read-only. Each class is
# constructed with ``(bus, storage)``.
_BUILTIN_HANDLER_FACTORIES: dict[str, type[ToolHandler]] = {
    "cloudtap": CloudtapTool,
}


class ToolRegistry:
    """Loads tool manifests and dispatches their actions to handlers."""

    def __init__(self, tools_dir: Path, bus: EventBus, storage: Storage | None = None) -> None:
        self._tools_dir = tools_dir
        self._bus = bus
        self._storage = storage
        self._manifests: dict[str, ToolManifest] = {}
        self._handlers: dict[str, ToolHandler] = {}

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
            if factory is not None:
                manifest.runnable = True
                self._handlers[manifest.id] = factory(self._bus, self._storage)
            else:
                manifest.runnable = False
                log.info(
                    "Tool '%s' has no built-in handler; listing it read-only.", manifest.id
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

    # ── lifecycle ────────────────────────────────────────────────────────

    async def shutdown_all(self) -> None:
        for tool_id, handler in self._handlers.items():
            try:
                await handler.shutdown()
            except Exception:  # pragma: no cover — defensive
                log.exception("Tool '%s' raised during shutdown.", tool_id)
