"""ChatGPT UI child-agent pool.

A ChatGPT parent may delegate bounded squad work to real chatgpt.com chats
instead of local/vendor CLI runtimes. One persistent Chromium context owns the
signed-in account; each child gets its own page so generations can run in
parallel without competing for a Chromium user-data-dir lock.

The pool deliberately requires two operator-owned setup artifacts under the
Synapse data directory:

* chatgpt-browser-profile/ -- a Playwright persistent profile that has been
  signed into chatgpt.com once by the account owner.
* chatgpt-connector-launch-url.txt -- the ChatGPT plugin-detail URL for the
  Synapse connector. A child opens that page, clicks "Try in chat", switches
  from Work to normal Chat, and only then receives its task.

No OpenAI password, cookie, or raw browser credential is copied into Synapse
project memory or a child prompt.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import chatgpt_browser_runtime as browser_runtime


PROFILE_DIRNAME = "chatgpt-browser-profile"
CONNECTOR_LAUNCH_URL_FILENAME = "chatgpt-connector-launch-url.txt"
WORKER_PROJECT_URL_FILENAME = "chatgpt-worker-project-url.txt"
WORKER_PROJECT_NAME = "Synapse2GPT Workers"


@dataclass
class ChatGPTChildResult:
    worker_id: str
    ok: bool = False
    reply: str = ""
    error: str = ""
    conversation_url: str = ""
    title_renamed: bool = False
    chatgpt_project_name: str = WORKER_PROJECT_NAME
    wall_clock_seconds: float = 0.0
    ui_duration_seconds: float | None = None


def profile_dir(data_dir: Path) -> Path:
    return (Path(data_dir) / PROFILE_DIRNAME).resolve()


def connector_launch_url_path(data_dir: Path) -> Path:
    return (Path(data_dir) / CONNECTOR_LAUNCH_URL_FILENAME).resolve()


def read_connector_launch_url(data_dir: Path) -> str:
    path = connector_launch_url_path(data_dir)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def worker_project_url_path(data_dir: Path) -> Path:
    return (Path(data_dir) / WORKER_PROJECT_URL_FILENAME).resolve()


def read_worker_project_url(data_dir: Path) -> str:
    path = worker_project_url_path(data_dir)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _store_worker_project_url(data_dir: Path, url: str) -> None:
    clean = url.strip()
    if not clean.startswith("https://chatgpt.com/"):
        return
    path = worker_project_url_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(clean + "\n", encoding="utf-8")


def readiness(data_dir: Path) -> dict[str, Any]:
    profile = profile_dir(data_dir)
    launch_url = read_connector_launch_url(data_dir)
    return {
        "runtime": "chatgpt_web",
        "profile_dir": str(profile),
        "profile_ready": browser_runtime.profile_available(profile),
        "connector_launch_url_configured": bool(launch_url),
        "worker_project_name": WORKER_PROJECT_NAME,
        "worker_project_url": read_worker_project_url(data_dir) or None,
        "ready": browser_runtime.profile_available(profile),
    }


async def _click_first_visible(locator: Any) -> bool:
    try:
        count = await locator.count()
    except Exception:
        return False
    for index in range(count):
        candidate = locator.nth(index)
        try:
            if await candidate.is_visible():
                await candidate.click()
                return True
        except Exception:
            continue
    return False


async def open_connector_chat(page: Any, launch_url: str) -> str | None:
    """Navigate through ChatGPT's connector detail page into a normal Chat."""

    try:
        await page.goto(launch_url, wait_until="domcontentloaded")
    except Exception as exc:
        return f"could not open the Synapse connector page in ChatGPT: {type(exc).__name__}: {exc}"

    current_url = str(getattr(page, "url", "") or "")
    if "/auth/" in current_url or "/login" in current_url:
        return (
            "ChatGPT browser profile is not signed in. Open the dedicated Synapse "
            "ChatGPT profile once, sign in manually, then retry."
        )

    try_in_chat = page.get_by_role("button", name="Try in chat")
    if not await _click_first_visible(try_in_chat):
        try_in_chat = page.get_by_role("link", name="Try in chat")
        if not await _click_first_visible(try_in_chat):
            return (
                "The configured ChatGPT connector page did not expose 'Try in chat'. "
                "Refresh chatgpt-connector-launch-url.txt from the Synapse plugin detail page."
            )

    try:
        await page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass

    chat_tab = page.get_by_role("tab", name="Chat")
    switched = await _click_first_visible(chat_tab)
    if not switched:
        chat_tab = page.get_by_role("button", name="Chat")
        switched = await _click_first_visible(chat_tab)
    if not switched:
        try:
            if await page.locator(browser_runtime._COMPOSER_SELECTOR).count() == 0:
                return (
                    "ChatGPT opened the connector but no normal Chat composer was found. "
                    "The Work/Chat switcher may have changed."
                )
        except Exception as exc:
            return f"could not verify the ChatGPT composer: {type(exc).__name__}: {exc}"

    return None



async def open_worker_project_chat(
    page: Any,
    data_dir: Path,
    *,
    conversation_url: str | None = None,
) -> str | None:
    """Open an existing worker or create a fresh chat inside Synapse2GPT Workers."""

    if conversation_url:
        try:
            await page.goto(conversation_url, wait_until="domcontentloaded")
        except Exception as exc:
            return (
                "could not resume the stored ChatGPT worker conversation: "
                f"{type(exc).__name__}: {exc}"
            )
        current_url = str(getattr(page, "url", "") or "")
        if "/auth/" in current_url or "/login" in current_url:
            return (
                "ChatGPT browser profile is no longer signed in. Open the dedicated "
                "Synapse ChatGPT profile once, sign in manually, then retry."
            )
        return None

    configured = read_worker_project_url(data_dir)
    try:
        await page.goto(configured or "https://chatgpt.com/", wait_until="domcontentloaded")
    except Exception as exc:
        return f"could not open ChatGPT for worker project discovery: {type(exc).__name__}: {exc}"

    current_url = str(getattr(page, "url", "") or "")
    if "/auth/" in current_url or "/login" in current_url:
        return (
            "ChatGPT browser profile is not signed in. Open the dedicated Synapse "
            "ChatGPT profile once, sign in manually, then retry."
        )

    if not configured:
        project_link = page.get_by_role("link", name=WORKER_PROJECT_NAME)
        found = await _click_first_visible(project_link)
        if not found:
            project_button = page.get_by_role("button", name=WORKER_PROJECT_NAME)
            found = await _click_first_visible(project_button)
        if not found:
            create_control = page.get_by_role("button", name="New project")
            if not await _click_first_visible(create_control):
                create_control = page.get_by_role("link", name="New project")
                if not await _click_first_visible(create_control):
                    create_control = page.get_by_role("button", name="Create project")
                    if not await _click_first_visible(create_control):
                        return (
                            f"ChatGPT project {WORKER_PROJECT_NAME!r} was not found and the "
                            "current UI exposed no New project control."
                        )
            try:
                name_input = page.locator(
                    'input[placeholder*="project" i], input[name*="name" i]'
                ).first
                await name_input.fill(WORKER_PROJECT_NAME)
            except Exception as exc:
                return f"could not name the ChatGPT worker project: {type(exc).__name__}: {exc}"
            created = await _click_first_visible(page.get_by_role("button", name="Create"))
            if not created:
                created = await _click_first_visible(
                    page.get_by_role("button", name="Create project")
                )
            if not created:
                return "ChatGPT worker project form opened but no Create control was found."
        try:
            await page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass
        current_url = str(getattr(page, "url", "") or "")
        _store_worker_project_url(data_dir, current_url)

    # The project home may itself expose a blank composer. Prefer an explicit
    # New chat control when one exists so every new work item starts clean.
    new_chat = page.get_by_role("button", name="New chat")
    opened = await _click_first_visible(new_chat)
    if not opened:
        opened = await _click_first_visible(page.get_by_role("link", name="New chat"))
    if opened:
        try:
            await page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass

    try:
        if await page.locator(browser_runtime._COMPOSER_SELECTOR).count() == 0:
            return (
                f"Opened {WORKER_PROJECT_NAME!r}, but no ChatGPT composer was found. "
                "The Projects UI may have changed."
            )
    except Exception as exc:
        return f"could not verify the worker-project composer: {type(exc).__name__}: {exc}"
    return None


async def rename_current_chat(page: Any, title: str) -> bool:
    """Best-effort rename while generation continues; never fail useful work."""

    clean = " ".join(title.split())[:160]
    if not clean:
        return False
    try:
        controls = [
            'button[data-testid="conversation-options-button"]',
            'button[aria-label*="conversation options" i]',
            'button[aria-label*="chat options" i]',
        ]
        opened = False
        for selector in controls:
            if await _click_first_visible(page.locator(selector)):
                opened = True
                break
        if not opened:
            return False
        rename = page.get_by_role("menuitem", name="Rename")
        if not await _click_first_visible(rename):
            if not await _click_first_visible(page.get_by_role("button", name="Rename")):
                return False
        field = page.locator(
            'input[aria-label*="rename" i], input[placeholder*="name" i]'
        ).first
        await field.fill(clean)
        if await _click_first_visible(page.get_by_role("button", name="Save")):
            return True
        return await _click_first_visible(page.get_by_role("button", name="Rename"))
    except Exception:
        return False


class ChatGPTBrowserPool:
    """One signed-in ChatGPT browser context with one page per child worker."""

    def __init__(self, data_dir: Path, *, headless: bool = True) -> None:
        self.data_dir = Path(data_dir)
        self.headless = headless
        self._playwright: Any = None
        self._context: Any = None
        self._start_lock = asyncio.Lock()
        self._pages: dict[str, Any] = {}

    @property
    def active_worker_ids(self) -> tuple[str, ...]:
        return tuple(self._pages)

    async def _ensure_started(self) -> str | None:
        state = readiness(self.data_dir)
        if not state["profile_ready"]:
            return (
                f"ChatGPT UI child agents require a signed-in browser profile at "
                f"{state['profile_dir']}. No CLI fallback will be used."
            )
        if self._context is not None:
            return None

        async with self._start_lock:
            if self._context is not None:
                return None
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                return "playwright is not installed; ChatGPT UI child agents cannot start."

            try:
                self._playwright = await async_playwright().start()
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir(self.data_dir)),
                    headless=self.headless,
                )
            except Exception as exc:
                if self._playwright is not None:
                    try:
                        await self._playwright.stop()
                    except Exception:
                        pass
                self._playwright = None
                self._context = None
                return f"could not start the ChatGPT browser context: {type(exc).__name__}: {exc}"
        return None

    async def run_child(
        self,
        worker_id: str,
        prompt: str,
        *,
        timeout: float = browser_runtime.DEFAULT_TIMEOUT_SECONDS,
        conversation_url: str | None = None,
        desired_title: str = "",
    ) -> ChatGPTChildResult:
        started = time.monotonic()
        result = ChatGPTChildResult(worker_id=worker_id)
        start_error = await self._ensure_started()
        if start_error:
            result.error = start_error
            result.wall_clock_seconds = round(max(0.0, time.monotonic() - started), 3)
            return result

        launch_url = read_connector_launch_url(self.data_dir)
        page = await self._context.new_page()
        self._pages[worker_id] = page
        try:
            project_error = await open_worker_project_chat(
                page,
                self.data_dir,
                conversation_url=conversation_url,
            )
            if project_error:
                result.error = project_error
                return result

            # Referring to a connected app in the prompt is supported by ChatGPT;
            # this keeps the worker inside its Project instead of using "Try in chat"
            # (which creates a top-level conversation outside the Project).
            app_prompt = (
                "Use the connected Synapse app/connector for project and tool actions "
                "required by this task.\n\n" + prompt
            )
            send_error: str | None = None
            for _attempt in range(1, browser_runtime.MAX_SEND_ATTEMPTS + 1):
                send_error = await browser_runtime._send_and_confirm_started(page, app_prompt)
                if send_error is None:
                    break
            if send_error is not None:
                result.error = (
                    f"failed to send ChatGPT child prompt after "
                    f"{browser_runtime.MAX_SEND_ATTEMPTS} attempt(s): {send_error}"
                )
                return result

            result.conversation_url = str(getattr(page, "url", "") or "")
            if desired_title:
                result.title_renamed = await rename_current_chat(page, desired_title)
            reply = await browser_runtime._wait_for_reply(page, timeout=timeout)
            if reply is None:
                if await browser_runtime.conversation_length_limit_reached(page):
                    result.error = "ChatGPT child conversation hit its maximum length."
                else:
                    result.error = f"ChatGPT child returned no reply within {timeout:g}s."
                return result

            result.ok = True
            result.reply = reply
            return result
        except asyncio.CancelledError:
            result.error = "ChatGPT child was cancelled."
            raise
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            return result
        finally:
            result.wall_clock_seconds = round(max(0.0, time.monotonic() - started), 3)
            if result.ok:
                try:
                    result.ui_duration_seconds = await browser_runtime.extract_worked_for_seconds(page)
                except Exception:
                    result.ui_duration_seconds = None
            self._pages.pop(worker_id, None)
            try:
                await page.close()
            except Exception:
                pass

    async def cancel(self, worker_id: str) -> bool:
        page = self._pages.get(worker_id)
        if page is None:
            return False
        try:
            await page.close()
        except Exception:
            pass
        self._pages.pop(worker_id, None)
        return True

    async def close(self) -> None:
        for worker_id in list(self._pages):
            await self.cancel(worker_id)
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
