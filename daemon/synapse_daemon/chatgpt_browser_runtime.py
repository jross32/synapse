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
* Sending is not self-evident from a `type()`/`press("Enter")` call succeeding -- both can
  report success while the text never actually reached the composer (e.g. a stale locator
  right after a navigation). Left unverified, that means silently waiting the full
  DEFAULT_TIMEOUT_SECONDS for a reply that was never going to come, because nothing was ever
  sent. Confirmed for real driving this exact UI (RackPilot's build loop, a sibling project
  using a different toolset -- see workflow-chatgpt-delegated-builds.md section 2c). Every
  send here is verified both before (composer content read back and compared to what was
  typed) and shortly after (stop button or cleared composer, within seconds, not minutes) --
  see `_send_and_confirm_started()`.
* A conversation can hit ChatGPT's own hard length ceiling ("You've reached the maximum
  length for this conversation, but you can keep talking by starting a new chat.") -- a
  PERMANENT condition, not a stall: nothing this module can do makes that conversation accept
  another message again. Confirmed for real the same night as the point above, on the same
  sibling project's build thread, right after dozens of turns and hundreds of tool calls.
  Critically, the platform's own "Start new chat" button does NOT preserve context -- it just
  opens a brand-new conversation with the caller's last message pre-filled as a courtesy, with
  no memory of anything that came before. The only way to continue with context intact is
  "Branch in new chat" from a specific message (hover it -> More actions -> Branch in new
  chat) -- a manual UI action this module detects but does not automate (see
  `conversation_length_limit_reached()`); automating the branch itself was attempted by hand
  this same night with an interactive browser tool and proved unreliable enough (silent
  no-ops on a heavily-loaded tab) that it isn't shipped here without being provable live.

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
import re
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

SEND_VERIFY_TIMEOUT_SECONDS = 12.0
"""How long to wait, right after pressing Enter, for visible proof the send actually
registered (composer cleared and/or the stop button appeared) -- found the hard way in a
sibling project driving the same chatgpt.com UI via a different toolset (RackPilot's build
loop, see workflow-chatgpt-delegated-builds.md section 2c): a `type()` call can report
success while the composer silently never received the text, so the follow-up Enter sends
nothing. Waiting the full DEFAULT_TIMEOUT_SECONDS to discover that is much too slow -- this
catches it in seconds so a caller can retry instead of sitting idle for up to 20 minutes."""

MAX_SEND_ATTEMPTS = 2
"""Retry the whole type-and-send sequence once before giving up, in case the first attempt
hit a transient focus/render glitch (e.g. right after a navigation) rather than a real
problem -- retrying also clears any stale leftover text first, so a retry never appends onto
a failed prior attempt's partial content."""

_SEND_BUTTON_SELECTOR = 'button[data-testid="send-button"]'
_STOP_BUTTON_SELECTOR = 'button[data-testid="stop-button"], button[aria-label*="Stop" i]'
_COMPOSER_SELECTOR = '#prompt-textarea, div[contenteditable="true"]'
_ASSISTANT_MESSAGE_SELECTOR = '[data-message-author-role="assistant"]'

_WORKED_FOR_RE = re.compile(
    r"\bworked\s+for\s+(?:(?P<hours>\d+)h\s*)?"
    r"(?:(?P<minutes>\d+)m\s*)?(?:(?P<seconds>\d+)s)?\b",
    re.IGNORECASE,
)


def parse_worked_for_seconds(text: str) -> float | None:
    """Parse ChatGPT/agent UI timing such as Worked for 3m 8s.

    The observer treats this as a preferred display-derived duration. If the
    UI omits it or changes format, callers fall back to the controller's
    wall-clock measurement rather than inventing a value.
    """
    matches = list(_WORKED_FOR_RE.finditer(text or ""))
    if not matches:
        return None
    match = matches[-1]
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total = hours * 3600 + minutes * 60 + seconds
    return float(total) if total >= 0 else None


async def extract_worked_for_seconds(page: Any) -> float | None:
    """Best-effort read of the most recent visible Worked for UI text."""
    try:
        messages = page.locator(_ASSISTANT_MESSAGE_SELECTOR)
        count = await messages.count()
        if count:
            value = parse_worked_for_seconds(await messages.nth(count - 1).inner_text())
            if value is not None:
                return value
        return parse_worked_for_seconds(await page.locator("body").inner_text())
    except Exception:  # noqa: BLE001 -- timing metadata must never break useful work
        return None


_LENGTH_LIMIT_TEXT = "reached the maximum length for this conversation"
"""Substring of OpenAI's own message when a conversation hits its hard length ceiling. Lower-
cased to match case-insensitively against the page's own text."""


async def conversation_length_limit_reached(page: Any) -> bool:
    """Whether this conversation has hit ChatGPT's hard length ceiling and can no longer accept
    new messages -- a distinct, PERMANENT failure mode, unlike a stall or a slow reply that
    will eventually resolve. Checking this explicitly turns what would otherwise be a wasted
    DEFAULT_TIMEOUT_SECONDS wait (or a pointless retry loop) into an immediate, actionable
    error that names the real problem instead of "no reply" / "stalled".
    """
    try:
        text = await page.locator("body").inner_text()
    except Exception:  # noqa: BLE001
        return False
    return _LENGTH_LIMIT_TEXT in text.lower()


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


async def _composer_text(page: Any) -> str:
    """Read back what the composer actually contains right now.

    A contenteditable's placeholder ("Ask ChatGPT") is CSS-rendered, not real DOM text, so an
    empty result here reliably means "nothing landed", not "showing a placeholder" -- this is
    what lets a caller tell the two apart without guessing.
    """
    try:
        return await page.locator(_COMPOSER_SELECTOR).first.inner_text()
    except Exception:  # noqa: BLE001
        return ""


def _typed_text_landed(typed: str, readback: str) -> bool:
    """Whether the composer's actual content is consistent with what was just typed.

    Exact matching is too strict -- a contenteditable can normalize whitespace/line-break
    representation differently than the source string. This only needs to catch the real
    failure modes found in practice: the composer ending up completely empty (nothing landed
    at all) or drastically short (typing got interrupted partway through) after a `type()`
    call that itself reported success with no error.
    """
    typed_norm = "".join(typed.split())
    readback_norm = "".join(readback.split())
    if not typed_norm:
        return True
    if not readback_norm:
        return False
    return len(readback_norm) >= 0.5 * len(typed_norm)


async def _clear_composer(page: Any) -> None:
    """Select-all and delete, so a retry never appends onto stale leftover content from a
    prior failed attempt -- the same contamination the delegated-build playbooks warn about
    when a human drives this exact UI by hand."""
    composer = page.locator(_COMPOSER_SELECTOR).first
    await composer.click()
    await page.keyboard.press("ControlOrMeta+A")
    await page.keyboard.press("Delete")


async def _send_and_confirm_started(page: Any, prompt: str) -> str | None:
    """Type the prompt, send it, and confirm generation actually started.

    Returns None on success, or a short diagnostic string on failure (the caller decides
    whether to retry). Two things are verified before this trusts that the send happened --
    never a `type()`/`press()` return value alone, since both can report success while
    nothing actually reached the page:
    1. Pre-send: the composer's real content, read back from the page, is consistent with
       what was just typed.
    2. Post-send: within SEND_VERIFY_TIMEOUT_SECONDS, either the stop button appears or the
       composer clears -- proof the message was accepted, not just that Enter was pressed
       into a page that silently ignored it.
    """
    if await conversation_length_limit_reached(page):
        return (
            "conversation has hit ChatGPT's maximum length and can no longer accept messages -- "
            "branch to a new conversation (hover a message -> More actions -> Branch in new "
            "chat) before continuing"
        )

    await _clear_composer(page)
    await _type_multiline(page, prompt)

    landed = await _composer_text(page)
    if not _typed_text_landed(prompt, landed):
        return f"composer content after typing did not match the prompt ({len(landed)} chars read back)"

    await page.keyboard.press("Enter")

    deadline = time.time() + SEND_VERIFY_TIMEOUT_SECONDS
    while time.time() < deadline:
        stop_visible = await page.locator(_STOP_BUTTON_SELECTOR).count()
        remaining = await _composer_text(page)
        if stop_visible or not remaining.strip():
            return None
        await asyncio.sleep(0.5)

    return (
        "no sign the send registered (no stop button, composer still has content) within "
        f"{SEND_VERIFY_TIMEOUT_SECONDS:g}s"
    )


async def assistant_message_count(page: Any) -> int:
    """Return the number of assistant messages currently rendered in the conversation.

    Capturing this immediately before a send gives recovery code a durable lower bound: after
    reloading the same conversation we must observe a *new* assistant message before declaring
    that the just-sent turn succeeded. Without this guard, a recovered tab could accidentally
    return the previous turn's already-complete answer as if it belonged to the current task.
    """
    try:
        return int(await page.locator(_ASSISTANT_MESSAGE_SELECTOR).count())
    except Exception:  # noqa: BLE001 -- observation metadata must not crash the worker
        return 0


async def _wait_for_reply(
    page: Any,
    *,
    timeout: float,
    minimum_message_count: int | None = None,
) -> str | None:
    """Poll until the current ChatGPT turn has a completed assistant reply, or give up.

    Two clocks, not one: an overall timeout (a very long real turn is normal here) and a
    stall timeout (the reply text must keep growing, or something is stuck -- the "frozen
    tab" failure mode the playbooks already document, where the process is alive but nothing
    is happening). ``minimum_message_count`` is used by safe recovery after a reload so an
    older assistant answer can never be mistaken for the reply to the prompt we just sent.
    """
    deadline = time.time() + timeout
    last_length = -1
    last_growth = time.time()

    while time.time() < deadline:
        if await conversation_length_limit_reached(page):
            break  # permanent condition -- no point waiting out the rest of the timeout

        stop_visible = await page.locator(_STOP_BUTTON_SELECTOR).count()
        messages = page.locator(_ASSISTANT_MESSAGE_SELECTOR)
        count = await messages.count()
        has_current_reply = minimum_message_count is None or count >= minimum_message_count
        current_text = (
            await messages.nth(count - 1).inner_text()
            if count and has_current_reply
            else ""
        )

        if len(current_text) != last_length:
            last_length = len(current_text)
            last_growth = time.time()
        elif time.time() - last_growth > STALL_TIMEOUT_SECONDS:
            # A frozen ChatGPT tab can leave the Stop button visible forever. Treat
            # sustained lack of observable reply growth as the stall signal rather
            # than trusting that button alone. The caller may safely reload/re-observe
            # the same conversation without resending the already-confirmed prompt.
            break

        if stop_visible == 0 and has_current_reply and current_text:
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

                send_error: str | None = None
                for _attempt in range(1, MAX_SEND_ATTEMPTS + 1):
                    send_error = await _send_and_confirm_started(page, prompt)
                    if send_error is None:
                        break

                if send_error is not None:
                    result.error = (
                        f"failed to send prompt after {MAX_SEND_ATTEMPTS} attempt(s): {send_error}")
                else:
                    reply_text = await _wait_for_reply(page, timeout=timeout)
                    if reply_text is None:
                        if await conversation_length_limit_reached(page):
                            result.error = (
                                "conversation has hit ChatGPT's maximum length and can no longer "
                                "accept messages -- branch to a new conversation (hover a "
                                "message -> More actions -> Branch in new chat) before "
                                "continuing; this module does not automate that step"
                            )
                        else:
                            result.error = (
                                f"no reply within {timeout:g}s "
                                "(stalled, or generation never started)"
                            )
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
