"""ChatGPT UI child-agent pool.

A ChatGPT parent may delegate bounded squad work to real chatgpt.com chats
instead of local/vendor CLI runtimes. One persistent Chromium context owns the
signed-in account; each child gets its own page so generations can run in
parallel without competing for a Chromium user-data-dir lock.

The pool requires one operator-owned setup artifact under the Synapse data
directory: ``chatgpt-browser-profile/``, a dedicated Chromium profile that the
account owner signs into ChatGPT once. New workers are created directly inside
the private ``Synapse2GPT Workers`` ChatGPT Project; existing workers resume by
their stored conversation URL. The worker prompt references the connected
Synapse app by name so the chat stays inside the Project.

No OpenAI password, cookie, or raw browser credential is copied into Synapse
project memory or a child prompt.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psutil

from . import chatgpt_browser_runtime as browser_runtime

PROFILE_DIRNAME = "chatgpt-browser-profile"
CONNECTOR_LAUNCH_URL_FILENAME = "chatgpt-connector-launch-url.txt"
WORKER_PROJECT_URL_FILENAME = "chatgpt-worker-project-url.txt"
WORKER_PROJECT_NAME = "Synapse2GPT Workers"
SETUP_URL = "https://chatgpt.com/"
DEFAULT_BROWSER_CHANNEL = "chrome"
BACKGROUND_BROWSER_ARGS = ("--window-position=-32000,-32000", "--window-size=1100,820")
CANONICAL_CONVERSATION_URL_TIMEOUT_SECONDS = 30.0
CANONICAL_CONVERSATION_URL_POLL_SECONDS = 0.25


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
    recovery_attempted: bool = False
    recovery_succeeded: bool = False
    recovery_error: str = ""


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


def is_durable_conversation_url(url: str) -> bool:
    """Return True only for a reopenable ChatGPT ``/c/<server-id>`` URL.

    New chats briefly use optimistic client ids such as ``/c/WEB:<uuid>``. Those URLs appear in
    Chrome history but collapse to ChatGPT home when reopened. ChatGPT later replaces them with
    the canonical server conversation id. Never put an optimistic URL in the durable worker
    registry, recovery path, reuse path, or archive path.
    """
    clean = (url or "").strip()
    if not clean:
        return False
    try:
        parsed = urlparse(clean)
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.netloc.lower() != "chatgpt.com":
        return False
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0] != "c":
        return False
    conversation_id = parts[1].strip()
    return bool(conversation_id) and not conversation_id.upper().startswith("WEB:")


async def wait_for_durable_conversation_url(
    page: Any,
    *,
    timeout: float = CANONICAL_CONVERSATION_URL_TIMEOUT_SECONDS,
) -> str:
    """Wait briefly for ChatGPT to replace its optimistic URL with the canonical one."""
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        current = str(getattr(page, "url", "") or "").strip()
        if is_durable_conversation_url(current):
            return current
        if time.monotonic() >= deadline:
            return ""
        await asyncio.sleep(CANONICAL_CONVERSATION_URL_POLL_SECONDS)


def readiness(data_dir: Path) -> dict[str, Any]:
    profile = profile_dir(data_dir)
    launch_url = read_connector_launch_url(data_dir)
    profile_ready = browser_runtime.profile_available(profile)
    project_url = read_worker_project_url(data_dir)
    return {
        "runtime": "chatgpt_web",
        "profile_dir": str(profile),
        "profile_ready": profile_ready,
        "connector_launch_url_configured": bool(launch_url),
        "worker_project_name": WORKER_PROJECT_NAME,
        "worker_project_url": project_url or None,
        "ready": profile_ready,
        "login_verified": False,
        "login_verification_note": "Profile presence does not establish a live ChatGPT session; run a browser-authenticated smoke check.",
        "setup_complete": profile_ready and bool(project_url),
        "requires_account_owner_login_or_project_bootstrap": not (profile_ready and bool(project_url)),
        "recommended_project_memory": "default",
        "recommended_project_sharing": "private",
        "setup_endpoint": "/api/v1/chatgpt-workers/setup-browser",
    }


def _browser_candidates() -> list[Path]:
    candidates: list[Path] = []
    for env_name, relative in (
        ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
        ("PROGRAMFILES(X86)", "Google/Chrome/Application/chrome.exe"),
        ("LOCALAPPDATA", "Google/Chrome/Application/chrome.exe"),
        ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
        ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
    ):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / Path(relative))
    for name in ("chrome", "google-chrome", "msedge", "chromium"):
        resolved = shutil.which(name)
        if resolved:
            candidates.append(Path(resolved))
    return candidates


def find_setup_browser() -> Path | None:
    """Return an installed Chromium-family browser without opening any user profile."""

    for candidate in _browser_candidates():
        if candidate.exists():
            return candidate.resolve()
    return None


def setup_browser_argv(
    data_dir: Path, *, browser_executable: Path | None = None
) -> list[str]:
    """Build the visible one-time login command for Synapse's dedicated profile."""

    executable = browser_executable or find_setup_browser()
    if executable is None:
        return []
    return [
        str(executable),
        f"--user-data-dir={profile_dir(data_dir)}",
        "--profile-directory=Default",
        SETUP_URL,
    ]


def _running_setup_browser_pid(data_dir: Path) -> int | None:
    """Return the PID already using Synapse's dedicated ChatGPT profile, if any."""

    profile_arg = f"--user-data-dir={profile_dir(data_dir)}".casefold()
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            argv = [str(part) for part in (process.info.get("cmdline") or [])]
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if any(part.casefold() == profile_arg for part in argv):
            return int(process.info["pid"])
    return None


def launch_setup_browser(data_dir: Path) -> dict[str, Any]:
    """Open a visible dedicated ChatGPT profile for account-owner sign-in.

    This never reads or copies the operator's normal Chrome/Edge cookies, saved
    passwords, or tokens. The human performs the one-time ChatGPT login in the
    dedicated profile, closes that browser, and future workers reuse it.
    """

    profile = profile_dir(data_dir)
    profile.mkdir(parents=True, exist_ok=True)
    running_pid = _running_setup_browser_pid(data_dir)
    if running_pid is not None:
        return {
            "launched": False,
            "already_running": True,
            "pid": running_pid,
            "profile_dir": str(profile),
            "url": SETUP_URL,
            "worker_project_name": WORKER_PROJECT_NAME,
            "recommended_project_memory": "default",
            "instructions": "The dedicated ChatGPT setup browser is already open. Finish sign-in there, then close it before launching headless workers.",
        }
    argv = setup_browser_argv(data_dir)
    if not argv:
        return {
            "launched": False,
            "profile_dir": str(profile),
            "error": "No supported Chrome, Edge, or Chromium executable was found.",
        }
    try:
        process = subprocess.Popen(
            argv,
            cwd=str(profile.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as exc:
        return {
            "launched": False,
            "profile_dir": str(profile),
            "error": f"Could not open the ChatGPT setup browser: {type(exc).__name__}: {exc}",
        }
    return {
        "launched": True,
        "pid": process.pid,
        "profile_dir": str(profile),
        "url": SETUP_URL,
        "worker_project_name": WORKER_PROJECT_NAME,
        "recommended_project_memory": "default",
        "instructions": (
            "Sign into ChatGPT in this dedicated browser profile, then close the setup browser. "
            "The first worker launch will find or create the private Synapse2GPT Workers Project."
        ),
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


async def _human_verification_blocker(page: Any) -> str | None:
    """Detect anti-bot interstitials without attempting to solve or bypass them."""
    title = ""
    body = ""
    try:
        title = str(await page.title() or "")
    except Exception:
        pass
    try:
        locator = page.locator("body")
        inner_text = getattr(locator, "inner_text", None)
        if inner_text is not None:
            body = str(await inner_text(timeout=1000) or "")
    except Exception:
        pass
    evidence = (title + chr(10) + body).casefold()
    challenge_markers = (
        "just a moment",
        "verify you are human",
        "performing security verification",
        "checking your browser",
        "cloudflare",
    )
    if not any(marker in evidence for marker in challenge_markers):
        return None
    return (
        "ChatGPT/Cloudflare requires human verification in the dedicated Synapse "
        "browser profile. Open that profile, complete the verification manually, "
        "then retry the worker. Synapse will not automate or bypass human verification."
    )


async def open_connector_chat(page: Any, launch_url: str) -> str | None:
    """Navigate through ChatGPT's connector detail page into a normal Chat."""

    try:
        await page.goto(launch_url, wait_until="domcontentloaded")
    except Exception as exc:
        return f"could not open the Synapse connector page in ChatGPT: {type(exc).__name__}: {exc}"

    blocker = await _human_verification_blocker(page)
    if blocker:
        return blocker

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
            # ChatGPT's own Try-in-chat navigation encodes the plugin id in a
            # hints query. The dedicated worker profile history confirms this
            # route even on builds where the detail page omits the CTA.
            plugin_id = next(
                (part for part in launch_url.replace("?", "/").split("/") if part.startswith("plugin_asdk_app_")),
                "",
            )
            if plugin_id:
                plugin_id = plugin_id.removeprefix("plugin_")
                hint_url = f"https://chatgpt.com/?surface=work&hints=plugin%3A{plugin_id}"
                try:
                    await page.goto(hint_url, wait_until="domcontentloaded")
                except Exception as exc:
                    return f"could not open ChatGPT attached-plugin hint surface: {type(exc).__name__}: {exc}"
                blocker = await _human_verification_blocker(page)
                if blocker:
                    return blocker
            else:
                return (
                    "The configured ChatGPT connector page did not expose 'Try in chat' "
                    "and its URL did not contain a reusable Synapse plugin id."
                )

    try:
        await page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass

    blocker = await _human_verification_blocker(page)
    if blocker:
        return blocker

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



async def _connector_chip_visible(page: Any) -> bool:
    """Best-effort check that this conversation already has Synapse attached."""

    selectors = (
        'button[aria-label*="Synapse" i]',
        '[data-testid*="composer" i] button:has-text("Synapse")',
        '[data-testid*="composer" i] [role="button"]:has-text("Synapse")',
    )
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = await locator.count()
        except Exception:
            continue
        for index in range(count):
            try:
                if await locator.nth(index).is_visible():
                    return True
            except Exception:
                continue
    return False


async def _select_synapse_from_open_app_menu(page: Any) -> bool:
    """Select an already-connected Synapse app from the currently open ChatGPT menu.

    Current ChatGPT surfaces do not guarantee a separate app-search input. The ``+``
    menu may list connected apps directly, or expose them after an Apps/Plugins/More
    submenu. Prefer that semantic path before falling back to search.
    """

    for role in ("menuitem", "option", "button", "link"):
        try:
            if await _click_first_visible(page.get_by_role(role, name="Synapse")):
                return True
        except Exception:
            continue
    try:
        return await _click_first_visible(page.get_by_text("Synapse", exact=True))
    except Exception:
        return False


async def _visible_app_search(page: Any) -> Any | None:
    """Return a visible app/plugin search field when this ChatGPT build exposes one."""

    selectors = (
        'input[placeholder*="Search" i]',
        'input[aria-label*="Search" i]',
        'input[type="search"]',
        '[role="searchbox"]',
        'input[placeholder*="app" i]',
        'input[placeholder*="plugin" i]',
    )
    for selector in selectors:
        try:
            candidate = page.locator(selector).first
            if await candidate.count() and await candidate.is_visible():
                return candidate
        except Exception:
            continue
    return None


async def attach_synapse_connector(page: Any, *, launch_url: str = "") -> str | None:
    """Attach Synapse to the current ChatGPT conversation before sending work.

    ChatGPT app/connector attachment is conversation-scoped: merely mentioning a
    connected app in prompt text does not attach it to a fresh chat. The live UI
    flow verified by the operator is composer ``+`` -> app/plugin search ->
    ``Synapse``. This helper follows that flow with semantic fallbacks and fails
    closed rather than sending a tool-dependent worker prompt without Synapse.
    """

    if await _connector_chip_visible(page):
        return None

    menu_opened = False
    opener_selectors = (
        'button[data-testid*="composer" i][aria-label*="add" i]',
        'button[aria-label*="Add files" i]',
        'button[aria-label*="Add photos" i]',
        'button[aria-label*="tools" i]',
    )
    for selector in opener_selectors:
        try:
            if await _click_first_visible(page.locator(selector)):
                menu_opened = True
                break
        except Exception:
            continue
    if not menu_opened:
        for name in ("Add files and more", "Add photos & files", "Tools", "Add"):
            try:
                if await _click_first_visible(page.get_by_role("button", name=name)):
                    menu_opened = True
                    break
            except Exception:
                continue
    if not menu_opened:
        if launch_url:
            return await open_connector_chat(page, launch_url)
        return "ChatGPT composer exposed no app/connector menu; Synapse could not be attached."

    # Newer ChatGPT builds can list connected apps directly in the + menu, with no
    # dedicated search field at all. Prefer that path first.
    if await _select_synapse_from_open_app_menu(page):
        await asyncio.sleep(0.15)
        return None

    # Some builds require an Apps/Plugins/Connectors/More step. Open it, then try
    # direct selection again before assuming there must be a search input.
    search = await _visible_app_search(page)
    if search is None:
        category_opened = False
        for role in ("menuitem", "button", "link"):
            for name in (
                "Apps",
                "Plugins",
                "Connectors",
                "More apps",
                "More plugins",
                "More",
            ):
                try:
                    if await _click_first_visible(page.get_by_role(role, name=name)):
                        category_opened = True
                        break
                except Exception:
                    continue
            if category_opened:
                break
        if category_opened and await _select_synapse_from_open_app_menu(page):
            await asyncio.sleep(0.15)
            return None
        search = await _visible_app_search(page)

    if search is None:
        if launch_url:
            return await open_connector_chat(page, launch_url)
        return (
            "ChatGPT app/plugin menu opened, but Synapse was not listed directly and "
            "no app/plugin search field was exposed."
        )

    try:
        await search.fill("Synapse")
    except Exception as exc:
        return f"could not search ChatGPT apps/plugins for Synapse: {type(exc).__name__}: {exc}"

    if not await _select_synapse_from_open_app_menu(page):
        return "Synapse was not present in ChatGPT's app/plugin search results."

    # Give the composer a brief render turn, then verify when the current UI
    # exposes the attachment chip. A successful semantic click is still accepted
    # on builds whose chip has no accessible Synapse label.
    await asyncio.sleep(0.15)
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
    """One signed-in ChatGPT browser context with one page per child worker.

    The default is a real Chrome window positioned far off-screen rather than
    Chromium's true headless mode. ChatGPT/Cloudflare currently challenges the
    latter on this machine, while the off-screen browser preserves the normal
    signed-in web runtime without putting a window in the operator's way.
    Callers can still request ``headless=True`` explicitly for diagnostics.
    """

    def __init__(
        self,
        data_dir: Path,
        *,
        headless: bool = False,
        browser_channel: str | None = DEFAULT_BROWSER_CHANNEL,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.headless = headless
        self.browser_channel = browser_channel
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
                launch_kwargs: dict[str, Any] = {
                    "user_data_dir": str(profile_dir(self.data_dir)),
                    "headless": self.headless,
                }
                if not self.headless:
                    if self.browser_channel:
                        launch_kwargs["channel"] = self.browser_channel
                    launch_kwargs["args"] = list(BACKGROUND_BROWSER_ARGS)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    **launch_kwargs
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
        started_at = time.monotonic()
        result = ChatGPTChildResult(worker_id=worker_id)
        start_error = await self._ensure_started()
        if start_error:
            result.error = start_error
            result.wall_clock_seconds = max(0.0, time.monotonic() - started_at)
            return result

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

            connector_error = await attach_synapse_connector(
                page, launch_url=read_connector_launch_url(self.data_dir)
            )
            if connector_error:
                result.error = connector_error
                return result

            app_prompt = (
                "Use the attached Synapse app/connector for project and tool actions "
                "required by this task.\n\n" + prompt
            )
            assistant_count_before_send = await browser_runtime.assistant_message_count(page)
            minimum_reply_count = assistant_count_before_send + 1
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

            result.conversation_url = await wait_for_durable_conversation_url(page)
            if desired_title:
                result.title_renamed = await rename_current_chat(page, desired_title)
            reply = await browser_runtime._wait_for_reply(
                page, timeout=timeout, minimum_message_count=minimum_reply_count
            )
            if reply is None:
                if await browser_runtime.conversation_length_limit_reached(page):
                    result.error = "ChatGPT child conversation hit its maximum length."
                    return result

                # Safe recovery for a frozen/interrupted observer: the prompt was already
                # positively confirmed as sent, so NEVER resend it here. Re-open the exact
                # durable conversation URL and observe that same turn once more. The message
                # count floor prevents a previous assistant answer from being mistaken for
                # this turn after navigation.
                latest_durable_url = await wait_for_durable_conversation_url(page, timeout=5.0)
                if latest_durable_url:
                    result.conversation_url = latest_durable_url
                recovery_url = (
                    result.conversation_url
                    if is_durable_conversation_url(result.conversation_url)
                    else ""
                )
                if recovery_url:
                    result.recovery_attempted = True
                    try:
                        await page.goto(recovery_url, wait_until="domcontentloaded")
                        reply = await browser_runtime._wait_for_reply(
                            page,
                            timeout=min(120.0, max(10.0, float(timeout))),
                            minimum_message_count=minimum_reply_count,
                        )
                        result.recovery_succeeded = reply is not None
                    except Exception as exc:  # noqa: BLE001 -- preserve the original actionable failure
                        result.recovery_error = f"{type(exc).__name__}: {exc}"
                        reply = None

                if reply is None:
                    if await browser_runtime.conversation_length_limit_reached(page):
                        result.error = "ChatGPT child conversation hit its maximum length."
                    else:
                        if recovery_url:
                            result.error = (
                                "ChatGPT child did not yield a completed observable reply before the "
                                "browser observer/recovery deadline; one safe same-conversation "
                                "recovery observation was attempted without resending the prompt."
                            )
                        else:
                            result.error = (
                                "ChatGPT child did not yield a completed observable reply and ChatGPT "
                                "never exposed a durable canonical conversation URL for safe recovery. "
                                "The prompt was not resent."
                            )
                    return result

            latest_durable_url = await wait_for_durable_conversation_url(page, timeout=5.0)
            if latest_durable_url:
                result.conversation_url = latest_durable_url
            result.ok = True
            result.reply = reply
            result.ui_duration_seconds = await browser_runtime.extract_worked_for_seconds(page)
            return result
        except asyncio.CancelledError:
            result.error = "ChatGPT child was cancelled."
            raise
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            return result
        finally:
            result.wall_clock_seconds = max(0.0, time.monotonic() - started_at)
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
