"""Authenticated Playwright MCP execution path for ChatGPT worker conversations.

The browser lane is globally selected-tab based. All operations are serialized
through SharedWebscraperBrowser; never attach to an operator tab or copy a profile.
"""
from __future__ import annotations
import asyncio
import re
import time
from typing import Any
from .shared_webscraper_browser import SharedWebscraperBrowser

URL_RE = re.compile(r"https://chatgpt\.com/[^\s)\]]+/c/[a-zA-Z0-9-]+")
COMPOSER_RE = re.compile(r'textbox "Ask ChatGPT" \[ref=(e\d+)\]')
SEND_RE = re.compile(r'button "Send(?: message)?" \[ref=(e\d+)\]')


async def execute_mcp_chat(browser: SharedWebscraperBrowser, worker_id: str, prompt: str,
                           start_url: str, timeout: float = 600.0,
                           on_conversation=None) -> dict[str, Any]:
    """Return observable reply only; never assert code/tests/commit succeeded."""
    started = time.monotonic()
    tab = await browser.new_tab(worker_id, start_url)
    sent = False
    conversation_url = ""
    try:
        snapshot = await tab.call("browser_snapshot", {"depth": 12})
        match = COMPOSER_RE.search(snapshot)
        if not match:
            raise RuntimeError("Authenticated ChatGPT composer not available")
        await tab.call("browser_type", {"target": match.group(1), "text": prompt})
        snapshot = await tab.call("browser_snapshot", {"depth": 12})
        if prompt[:min(40, len(prompt))] not in snapshot:
            # Some snapshots omit editor contents. Do not send an unconfirmed prompt.
            raise RuntimeError("Cannot confirm prompt in ChatGPT composer; refusing send")
        send = SEND_RE.search(snapshot)
        if send:
            await tab.call("browser_click", {"target": send.group(1)})
        else:
            await tab.call("browser_press_key", {"key": "Enter"})
        sent = True
        previous = ""
        stable = 0
        while time.monotonic() - started < timeout:
            snapshot = await tab.call("browser_snapshot", {"depth": 16})
            url_match = URL_RE.search(snapshot)
            if url_match and not conversation_url:
                conversation_url = url_match.group(0)
                if on_conversation:
                    await on_conversation(conversation_url)
            # A completed UI turn must be confirmed by explicit status; no fixed-sleep success.
            complete = "Response complete" in snapshot and (
                'button "Regenerate response"' in snapshot or 'button "Copy"' in snapshot
            )
            if complete and snapshot == previous:
                stable += 1
            else:
                stable = 0
            if stable >= 1:
                return {"ok": True, "reply": snapshot, "conversation_url": conversation_url,
                        "sent": sent}
            previous = snapshot
            await asyncio.sleep(2)
        return {"ok": False, "error": "Timed out observing ChatGPT response; prompt not resent",
                "conversation_url": conversation_url, "sent": sent}
    finally:
        await tab.close()
