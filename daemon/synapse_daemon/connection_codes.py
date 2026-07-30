"""Connection status codes for AI sessions (ADR-0028, PLAN 5 Phase 1).

When an AI registers a coordination session (its "connection" to Synapse), Synapse
classifies the connection so the operator sees at a glance whether the AI came up with
**full control (green)**, is **connected but degraded (yellow)**, or **failed (red)** --
and, for anything other than green, a stable machine ``code`` plus a plain-language
explanation + remedy, so a future failed/degraded connection is self-diagnosing.

This module is pure data + logic (no daemon/DB deps) so the catalog is easy to test and
to serve to the UI (the notification center renders the colour + explanation) and to AIs
(``ai/context`` / the coordination snapshot report their own code).
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class ConnectionLevel(str, Enum):
    GREEN = "green"    # connected, full control, everything the session needs is up
    YELLOW = "yellow"  # connected but degraded -- some capability is unavailable
    RED = "red"        # the connection failed


class ConnectionCode(NamedTuple):
    code: str                 # stable machine key, e.g. "degraded.mcp_unavailable"
    level: ConnectionLevel
    title: str                # short human label for the notification
    explanation: str          # plain-language "what this means"
    remedy: str               # what to do about it ("" when nothing is needed)


_CATALOG: dict[str, ConnectionCode] = {}


def _register(code: str, level: ConnectionLevel, title: str, explanation: str, remedy: str) -> str:
    _CATALOG[code] = ConnectionCode(code, level, title, explanation, remedy)
    return code


# ── the catalog ─────────────────────────────────────────────────────────────
OK = _register(
    "ok",
    ConnectionLevel.GREEN,
    "Connected",
    "The AI registered a session and has full control over Synapse.",
    "",
)
DEGRADED_MCP_UNAVAILABLE = _register(
    "degraded.mcp_unavailable",
    ConnectionLevel.YELLOW,
    "Connected — some tools offline",
    "The AI is connected, but one or more enabled MCP servers it may rely on are not currently connected, "
    "so those tools are unavailable to it.",
    "Open Tools → MCP Servers and start the offline server(s).",
)
DEGRADED_NO_PROJECT = _register(
    "degraded.no_project",
    ConnectionLevel.YELLOW,
    "Connected — no project",
    "The AI registered without binding to a project, so project-scoped work (files, records, launches) "
    "isn't available for this session.",
    "Register the session with a valid project_id to enable project-scoped work.",
)
FAILED_INTERNAL = _register(
    "failed.internal",
    ConnectionLevel.RED,
    "Connection failed",
    "Synapse hit an internal error while registering the session, so the AI is not connected.",
    "Check the daemon log for the error and retry the connection.",
)


def get(code: str) -> ConnectionCode:
    """Look up a code; unknown codes degrade to failed.internal (never raises)."""
    return _CATALOG.get(code, _CATALOG[FAILED_INTERNAL])


def catalog() -> list[ConnectionCode]:
    """The full catalog (for the docs table / an API that serves the legend)."""
    return list(_CATALOG.values())


def classify(*, mcp_all_connected: bool = True, has_project: bool = True) -> ConnectionCode:
    """Pick the connection code from the daemon's signals at registration time.

    GREEN only when everything is up. Degraded conditions are checked most-severe-first
    and return the first that applies. (WAN/Cloudtap availability is *informational* for a
    local AI, not a degrader, so it doesn't lower the level here.)
    """
    if not mcp_all_connected:
        return get(DEGRADED_MCP_UNAVAILABLE)
    if not has_project:
        return get(DEGRADED_NO_PROJECT)
    return get(OK)
