"""Conservative, cooperative tab transport over an authenticated MCP Playwright server.

The MCP Playwright tools use a *global selected tab*. The lock covers every
selection and subsequent action, preventing workers using this adapter from
interleaving. Other independent MCP clients are not coordinated; therefore
production use requires exclusive control of the registered browser tool lane.
Never closes tabs that it did not create.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

ToolCall = Callable[[str, dict[str, Any]], Awaitable[Any]]
_LOCK = asyncio.Lock()
_TAB_INDEX = re.compile(r"^\s*-?\s*(\d+):\s*(.*)$", re.MULTILINE)
_PAGE_URL = re.compile(r"^- Page URL:\s*(\S+)", re.MULTILINE)


class SharedBrowserError(RuntimeError):
    pass


def _text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        if response.get("isError") or response.get("error"):
            raise SharedBrowserError(str(response.get("error") or response.get("content")))
        return "\n".join(str(c.get("text", "")) for c in response.get("content", []) if isinstance(c, dict)) or str(response)
    return str(response)


def _indices(response: Any) -> set[int]:
    return {int(m.group(1)) for m in _TAB_INDEX.finditer(_text(response))}


@dataclass
class OwnedTab:
    transport: "SharedWebscraperBrowser"
    index: int
    worker_id: str
    closed: bool = False

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        if self.closed:
            raise SharedBrowserError("tab lease already closed")
        if name not in {"browser_snapshot", "browser_navigate", "browser_type",
                        "browser_click", "browser_press_key"}:
            raise SharedBrowserError("browser tool not allowed for worker")
        async with _LOCK:
            await self.transport._assert_ownership(self.index, self.worker_id)
            await self.transport._call("browser_tabs", {"action": "select", "index": self.index})
            return _text(await self.transport._call(name, arguments))

    async def close(self) -> None:
        if self.closed:
            return
        async with _LOCK:
            if self.transport._owned.get(self.index) != self.worker_id:
                raise SharedBrowserError("tab ownership lost; refusing close")
            await self.transport._assert_ownership(self.index, self.worker_id)
            await self.transport._call("browser_tabs", {"action": "close", "index": self.index})
            self.transport._owned.pop(self.index, None)
            self.transport._owned_urls.pop(self.index, None)
            self.closed = True


class SharedWebscraperBrowser:
    """Adapter receives a configured, authorized Synapse MCP tool-call function.

    No profile path, cookies, passwords, CDP attachment or Chrome process changes.
    """
    def __init__(self, call_tool: ToolCall):
        self._call = call_tool
        self._owned: dict[int, str] = {}
        self._owned_urls: dict[int, str] = {}

    async def _assert_ownership(self, index: int, worker_id: str) -> None:
        if self._owned.get(index) != worker_id:
            raise SharedBrowserError("tab ownership lost")
        listing = _text(await self._call("browser_tabs", {"action": "list"}))
        lines = dict((int(m.group(1)), m.group(2)) for m in _TAB_INDEX.finditer(listing))
        expected = self._owned_urls.get(index)
        # The tab can legitimately navigate from the project home to its conversation.
        if index not in lines or (expected and expected not in lines[index] and
                not (expected.endswith("/project") and "chatgpt.com/" in lines[index])):
            raise SharedBrowserError("tab index shifted or replaced; refusing to act")

    async def new_tab(self, worker_id: str, url: str) -> OwnedTab:
        if not worker_id or not (url == "https://chatgpt.com/" or
                                 url.startswith("https://chatgpt.com/c/") or
                                 url.startswith("https://chatgpt.com/g/")):
            raise SharedBrowserError("invalid worker or untrusted navigation URL")
        async with _LOCK:
            before = _indices(await self._call("browser_tabs", {"action": "list"}))
            await self._call("browser_tabs", {"action": "new", "url": url})
            after = _indices(await self._call("browser_tabs", {"action": "list"}))
            created = after - before
            if len(created) != 1:
                raise SharedBrowserError("could not prove unique new tab ownership; no tab closed")
            index = created.pop()
            self._owned[index] = worker_id
            self._owned_urls[index] = url
            return OwnedTab(self, index, worker_id)

