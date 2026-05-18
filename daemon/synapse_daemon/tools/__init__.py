"""Built-in tool handlers (Milestone F · v0.1.9).

A *handler* is the compiled-in code behind a tool's manifest actions. The
:class:`~synapse_daemon.tools_registry.ToolRegistry` binds each handler to its
manifest by tool id. Third-party manifests dropped into ``tools/`` are listed
in the UI but never bind to a handler unless the daemon ships one — no
untrusted Python is ever imported. This is the "curated handler" half of the
hybrid plugin model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ToolState


class ToolHandler(ABC):
    """Base class for a built-in tool's action logic.

    Subclasses set :attr:`tool_id` to match their ``manifest.json`` and
    implement :meth:`run_action` + :meth:`state`. :meth:`shutdown` is called
    once when the daemon stops so a handler can release OS resources (kill a
    spawned tunnel, close a handle, …).
    """

    #: Must equal the ``id`` field of the tool's manifest.
    tool_id: str = ""

    @abstractmethod
    async def run_action(self, action_id: str, fields: dict) -> ToolState:
        """Run one manifest action and return the tool's new state."""

    @abstractmethod
    def state(self) -> ToolState:
        """Return the tool's current state without mutating anything."""

    async def shutdown(self) -> None:  # noqa: B027 — intentionally optional
        """Release resources on daemon exit. Default: nothing to do."""
        return None
