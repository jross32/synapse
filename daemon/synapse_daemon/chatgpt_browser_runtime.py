"""Run a prompt through a live, already-signed-in ChatGPT tab via Playwright, and read the
reply back.

This is the odd rung on the runtime ladder (see coder_runtimes.py): every other rung is a CLI
Synapse can `subprocess.run()` headlessly. ChatGPT Plus has no CLI and no free API -- the only
way to drive it without paying for the separate OpenAI API is the same thing a human does:
open chatgpt.com in a real, signed-in browser tab, type, and read the reply.

Learned by hand this session, driving the real chatgpt.com UI end to end to build FlipLedger
(see the chatgpt-autonomous-app-build and chatgpt-workflow-design-notes playbooks):

* The composer sends the message on a plain Enter. A multi-line prompt typed with literal
  "\\n" characters gets cut off after its first line, because the *first* newline fires a send
  before the rest is even typed -- proven directly: a multi-paragraph brief arrived as only
  its opening sentence. Line breaks inside a prompt must be Shift+Enter, never a bare Enter.
* The send button toggles between a stop-icon while generating and a send-icon once the reply
  is complete. That toggle, not a fixed sleep, is what "generation finished" means here.
* The tab can freeze mid-generation on a long tool-heavy turn (the "frozen tab" gotcha the
  playbooks already document). A stall timeout, not just an overall timeout, catches that: if
  the assistant's message stops growing for a while, something is stuck even though the
  process itself hasn't crashed.

NOT wired into coder_runtimes.DEFAULT_LADDER yet. Every other rung is a stateless subprocess
call against a CLI that's either installed or isn't; this one drives a *specific, already
signed-in browser profile* that a human has to create by logging in once. That's a one-time
manual step this module cannot perform on its own -- doing it programmatically would mean
entering someone's real password, which this codebase does not do -- not an autonomy
restriction. Once a profile is logged in, run_prompt() itself takes no human input and
returns like any other rung; it's promotable into the default ladder once proven live.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from .coder_runtimes import RuntimeResult

DEFAULT_TIMEOUT_SECONDS = 1200.0
"""ChatGPT turns doing real tool calls run long -- FlipLedger's improvement pass took up to
32 minutes for a single reply. A short timeout here would mistake "still working" for stuck."""

STALL_TIMEOUT_SECONDS = 180.0
"""No growth in the reply for this long, with no stop button visible, means stuck -- not slow."""

POLL_INTERVAL_SECONDS = 2.0

_SEND_BUTTON_SELECTOR = 'button[data-testid="send-button"]'
_STOP_BUTTON_SELECTOR = 'button[data-testid="stop-button"], button[aria-label*="Stop" i]'
_COMPOSER_SELECTOR = '#prompt-textarea, div[contenteditable="true"]'
_ASSISTANT_MESSAGE_SELECTOR = '[data-message-author-role="assistant"]'


def profile_available(profile_dir: Path) -> bool:
    """Whether a persistent browser profile with an existing ChatGPT login is set up.

    Present is not the same as still logged in (a session can expire), but an absent or empty
    profile directory is a definite "not usable yet" -- there is no way this rung can work
    without one, and checking the directory is cheap enough to do before launching a browser
    at all. Deliberately NOT covered by coder_runtimes.available(): that function resolves a
    binary on PATH, which is meaningless for a rung with no CLI -- callers wanting to know if
    this specific rung can run right now should call this function, not that one.
    """
    return profile_dir.exists() and any(profile_dir.iterdir())


async def _type_multiline(page: Any, text: str) -> None:
    """Type text into the ChatGPT composer without triggering a premature send.

    A literal newline in a typed string reaches the composer as a plain Enter, which sends
    the message immediately -- proven directly by hand this session: a multi-paragraph brief
    sent after only its first line, with everything after silently dropped. Shift+Enter
    inserts a line break without sending; only the very last line is followed by a real Enter,
    done by the caller once typing is complete.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line:
            await page.keyboard.type(line)
        if i < len(lines) - 1:
            await page.keyboard.press("Shift+Enter")


async def _wait_for_reply(page: Any, *, timeout: float) -> str | None:
    """Poll until the send button flips back from "stop" to "send", or give up.

    Two clocks, not one: an overall timeout (a very long real turn is normal here) and a
    stall timeout (the reply text must keep growing, or something is stuck -- the "frozen
    tab" failure mode the playbooks already document, where the process is alive but nothing
    is happening). Either one expiring is reported as "no reply", never guessed at as success.
    """
    deadline = time.time() + timeout
    last_length = -1
    last_growth = time.time()

    while time.time() < deadline:
        stop_visible = await page.locator(_STOP_BUTTON_SELECTOR).count()
        messages = page.locator(_ASSISTANT_MESSAGE_SELECTOR)
        count = await messages.count()
        current_text = await messages.nth(count - 1).inner_text() if count else ""

        if len(current_text) != last_length:
            last_length = len(current_text)
            last_growth = time.time()
        elif stop_visible == 0 and time.time() - last_growth > STALL_TIMEOUT_SECONDS:
            break  # not growing and not generating -- treat as stuck, stop waiting

        if stop_visible == 0 and current_text:
            return current_text

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return None


async def run_prompt(
    prompt: str,
    *,
    profile_dir: Path,
    conversation_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    headless: bool = True,
) -> RuntimeResult:
    """Send one prompt to a live ChatGPT tab and return its reply.

    Mirrors coder_runtimes.RuntimeResult's contract (ok/source/error/seconds) so this rung's
    output shape matches every other one, even though the mechanism underneath -- a real
    browser, not a subprocess -- is completely different. Never raises: every failure mode
    (no profile, playwright missing, navigation error, timeout) comes back as
    result.error, the same discipline write_module() already follows for its own rungs.
    """
    started = time.time()
    result = RuntimeResult(runtime="chatgpt_web")

    if not profile_available(profile_dir):
        result.error = (
            f"no ChatGPT browser profile at {profile_dir} -- this rung needs a one-time human "
            "login into a Playwright-controlled browser before it can run unattended. See the "
            "chatgpt-workflow-design-notes playbook."
        )
        result.seconds = round(time.time() - started, 1)
        return result

    try:
        from playwright.async_api import async_playwright  # noqa: PLC0415
    except ImportError:
        result.error = "playwright not installed"
        result.seconds = round(time.time() - started, 1)
        return result

    try:
        async with async_playwright() as pw:
            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir), headless=headless)
            try:
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto(
                    conversation_url or "https://chatgpt.com/", wait_until="domcontentloaded")

                composer = page.locator(_COMPOSER_SELECTOR).first
                await composer.click()
                await _type_multiline(page, prompt)
                await page.keyboard.press("Enter")

                reply_text = await _wait_for_reply(page, timeout=timeout)
                if reply_text is None:
                    result.error = (
                        f"no reply within {timeout:g}s (stalled, or generation never started)")
                else:
                    result.ok = True
                    result.source = reply_text
            finally:
                await ctx.close()
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"

    result.seconds = round(time.time() - started, 1)
    return result


def run_prompt_sync(
    prompt: str,
    *,
    profile_dir: Path,
    conversation_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    headless: bool = True,
) -> RuntimeResult:
    """Synchronous wrapper for callers (like write_module's own call sites) that aren't
    already inside an event loop."""
    return asyncio.run(run_prompt(
        prompt, profile_dir=profile_dir, conversation_url=conversation_url,
        timeout=timeout, headless=headless))
