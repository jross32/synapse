"""Selection-safe authenticated ChatGPT browser worker execution.

MCP Playwright selects tabs globally. Only tabs created by this transport are used.
Observe conversation identity and response completion conservatively; never resend a
prompt after it has been submitted.
"""
from __future__ import annotations
import asyncio
import re
import time
from typing import Any
from .shared_webscraper_browser import SharedWebscraperBrowser

_COMPOSER = re.compile(r'(?:textbox "(?:Ask ChatGPT|New chat in [^"]+|Message [^"]*)"[^\n]*\[ref=(e\d+)\])')
_SEND = re.compile(r'button "(?:Send|Send message)"[^\n]*\[ref=(e\d+)\]')
_DURABLE_URL = re.compile(r'https://chatgpt\.com/[^\s)\]<>]+/c/[A-Za-z0-9-]+')
_PAGE_URL = re.compile(r'^- Page URL:\s*(\S+)', re.MULTILINE)

def conversation_url(snapshot: str) -> str:
    match = _PAGE_URL.search(snapshot)
    if match and _DURABLE_URL.fullmatch(match.group(1)):
        return match.group(1)
    return ""

def _page(snapshot: str) -> str:
    return snapshot.split("### Snapshot", 1)[-1]

def _response_done(snapshot: str) -> bool:
    page = _page(snapshot)
    return (
        "Response complete" in page
        and ('button "Copy"' in page or 'button "Regenerate response"' in page)
        and not ('button "Stop generating"' in page or 'button "Stop response"' in page)
    )

async def execute_mcp_chat(browser: SharedWebscraperBrowser, worker_id: str, prompt: str,
                           start_url: str, timeout: float = 600.0,
                           on_conversation=None, observe_only: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    tab = await browser.new_tab(worker_id, start_url)
    sent = False
    durable_url = start_url if observe_only and _DURABLE_URL.fullmatch(start_url) else ""
    try:
        snapshot = await tab.call("browser_snapshot", {"depth": 18})
        if not observe_only:
            match = _COMPOSER.search(_page(snapshot))
            if not match:
                raise RuntimeError("Authenticated ChatGPT project composer not found")
            await tab.call("browser_type", {"target": match.group(1), "text": prompt})
            snapshot = await tab.call("browser_snapshot", {"depth": 18})
            if prompt[:min(30, len(prompt))] not in snapshot:
                raise RuntimeError("Prompt not observable in composer; refusing unconfirmed send")
            send = _SEND.search(_page(snapshot))
            if send:
                await tab.call("browser_click", {"target": send.group(1)})
            else:
                raise RuntimeError("Send control not found; refusing ambiguous Enter action")
            sent = True
        elif not _DURABLE_URL.fullmatch(start_url):
            raise RuntimeError("Restart recovery requires exact durable conversation URL")

        previous = ""
        stable = 0
        while time.monotonic() - started < timeout:
            snapshot = await tab.call("browser_snapshot", {"depth": 24})
            observed_url = conversation_url(snapshot)
            if observed_url and observed_url != durable_url:
                if durable_url:
                    raise RuntimeError("Conversation identity changed during observation")
                durable_url = observed_url
                if on_conversation:
                    await on_conversation(durable_url)
            if _response_done(snapshot) and durable_url and snapshot == previous:
                stable += 1
            else:
                stable = 0
            if stable >= 1:
                return {"ok": True, "reply": _page(snapshot), "conversation_url": durable_url,
                        "sent": sent}
            previous = snapshot
            await asyncio.sleep(2)
        return {"ok": False, "error": "ChatGPT reply not confirmed before timeout; prompt not resent",
                "conversation_url": durable_url, "sent": sent}
    finally:
        await tab.close()
