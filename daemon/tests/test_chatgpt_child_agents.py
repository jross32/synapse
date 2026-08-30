"""Deterministic tests for ChatGPT UI child-agent orchestration."""

from __future__ import annotations

import asyncio
from pathlib import Path

from synapse_daemon import chatgpt_child_agents


def test_readiness_requires_signed_in_profile_not_legacy_connector_url(tmp_path: Path) -> None:
    state = chatgpt_child_agents.readiness(tmp_path)
    assert state["ready"] is False
    assert state["profile_ready"] is False
    assert state["connector_launch_url_configured"] is False

    profile = chatgpt_child_agents.profile_dir(tmp_path)
    profile.mkdir()
    (profile / "Default").mkdir()
    state = chatgpt_child_agents.readiness(tmp_path)
    assert state["profile_ready"] is True
    assert state["ready"] is True
    assert state["worker_project_name"] == "Synapse2GPT Workers"
    assert state["setup_complete"] is False
    assert state["requires_account_owner_login_or_project_bootstrap"] is True
    assert state["recommended_project_memory"] == "default"
    assert state["recommended_project_sharing"] == "private"

    # The old connector-detail URL can remain configured for legacy/manual flows,
    # but it is no longer a prerequisite for Project-native child spawning.
    chatgpt_child_agents.connector_launch_url_path(tmp_path).write_text(
        "https://chatgpt.com/test-connector", encoding="utf-8"
    )
    state = chatgpt_child_agents.readiness(tmp_path)
    assert state["connector_launch_url_configured"] is True
    assert state["ready"] is True


def test_missing_setup_never_falls_back_to_cli(tmp_path: Path) -> None:
    pool = chatgpt_child_agents.ChatGPTBrowserPool(tmp_path)
    result = asyncio.run(pool.run_child("child-1", "do work", timeout=1))

    assert result.ok is False
    assert result.worker_id == "child-1"
    assert "No CLI fallback will be used" in result.error
    assert result.wall_clock_seconds >= 0
    assert result.ui_duration_seconds is None
    assert pool.active_worker_ids == ()


class _FakeLocator:
    def __init__(self, *, visible: bool = True, count: int = 1) -> None:
        self.visible = visible
        self._count = count
        self.clicked = 0
        self.filled = ""

    @property
    def first(self):
        return self

    async def fill(self, value: str):
        self.filled = value

    async def count(self):
        return self._count

    def nth(self, _index: int):
        return self

    async def is_visible(self):
        return self.visible

    async def click(self):
        self.clicked += 1


class _FakePage:
    def __init__(self) -> None:
        self.url = "https://chatgpt.com/plugins/synapse"
        self.try_button = _FakeLocator()
        self.try_link = _FakeLocator(count=0)
        self.chat_tab = _FakeLocator()
        self.chat_button = _FakeLocator(count=0)
        self.composer = _FakeLocator(count=1)

    async def goto(self, url: str, wait_until: str):
        assert wait_until == "domcontentloaded"
        self.url = url

    def get_by_role(self, role: str, name: str):
        if role == "button" and name == "Try in chat":
            return self.try_button
        if role == "link" and name == "Try in chat":
            return self.try_link
        if role == "tab" and name == "Chat":
            return self.chat_tab
        if role == "button" and name == "Chat":
            return self.chat_button
        raise AssertionError((role, name))

    async def wait_for_load_state(self, _state: str):
        return None

    def locator(self, _selector: str):
        return self.composer


def test_open_connector_chat_uses_try_in_chat_then_normal_chat() -> None:
    page = _FakePage()
    error = asyncio.run(
        chatgpt_child_agents.open_connector_chat(
            page, "https://chatgpt.com/plugins/synapse"
        )
    )

    assert error is None
    assert page.try_button.clicked == 1
    assert page.chat_tab.clicked == 1


def test_open_connector_chat_rejects_logged_out_profile() -> None:
    page = _FakePage()

    async def logged_out_goto(url: str, wait_until: str):
        page.url = "https://chatgpt.com/auth/login"

    page.goto = logged_out_goto
    error = asyncio.run(
        chatgpt_child_agents.open_connector_chat(
            page, "https://chatgpt.com/plugins/synapse"
        )
    )

    assert error is not None
    assert "not signed in" in error


class _FakeProjectPage:
    def __init__(self) -> None:
        self.url = "https://chatgpt.com/"
        self.visited: list[str] = []
        self.new_chat = _FakeLocator()
        self.no_link = _FakeLocator(count=0)
        self.composer = _FakeLocator(count=1)

    async def goto(self, url: str, wait_until: str):
        assert wait_until == "domcontentloaded"
        self.visited.append(url)
        self.url = url

    async def wait_for_load_state(self, _state: str):
        return None

    def get_by_role(self, role: str, name: str):
        if role == "button" and name == "New chat":
            return self.new_chat
        if role == "link" and name == "New chat":
            return self.no_link
        raise AssertionError((role, name))

    def locator(self, _selector: str):
        return self.composer


def test_worker_project_url_opens_fresh_chat_inside_project(tmp_path: Path) -> None:
    project_url = "https://chatgpt.com/g/g-p-synapse2gpt/project"
    chatgpt_child_agents.worker_project_url_path(tmp_path).write_text(
        project_url, encoding="utf-8"
    )
    page = _FakeProjectPage()

    error = asyncio.run(
        chatgpt_child_agents.open_worker_project_chat(page, tmp_path)
    )

    assert error is None
    assert page.visited == [project_url]
    assert page.new_chat.clicked == 1


def test_existing_worker_url_resumes_directly_without_new_chat(tmp_path: Path) -> None:
    page = _FakeProjectPage()
    worker_url = "https://chatgpt.com/c/existing-worker"

    error = asyncio.run(
        chatgpt_child_agents.open_worker_project_chat(
            page, tmp_path, conversation_url=worker_url
        )
    )

    assert error is None
    assert page.visited == [worker_url]
    assert page.new_chat.clicked == 0


class _FakeRenamePage:
    def __init__(self) -> None:
        self.options = _FakeLocator()
        self.rename = _FakeLocator()
        self.field = _FakeLocator()
        self.save = _FakeLocator()

    def locator(self, selector: str):
        if selector == 'button[data-testid="conversation-options-button"]':
            return self.options
        if selector.startswith('input[aria-label'):
            return self.field
        return _FakeLocator(count=0)

    def get_by_role(self, role: str, name: str):
        if role == "menuitem" and name == "Rename":
            return self.rename
        if role == "button" and name == "Save":
            return self.save
        if role == "button" and name == "Rename":
            return _FakeLocator(count=0)
        raise AssertionError((role, name))


def test_worker_title_rename_is_best_effort_and_bounded() -> None:
    page = _FakeRenamePage()
    title = "QA ? RackPilot ? Login regression"

    renamed = asyncio.run(chatgpt_child_agents.rename_current_chat(page, title))

    assert renamed is True
    assert page.options.clicked == 1
    assert page.rename.clicked == 1
    assert page.field.filled == title
    assert page.save.clicked == 1


def test_setup_browser_argv_uses_only_dedicated_synapse_profile(tmp_path: Path) -> None:
    fake_browser = tmp_path / "chrome.exe"
    fake_browser.write_bytes(b"")

    argv = chatgpt_child_agents.setup_browser_argv(
        tmp_path, browser_executable=fake_browser
    )

    assert argv[0] == str(fake_browser)
    assert argv[-1] == "https://chatgpt.com/"
    assert f"--user-data-dir={chatgpt_child_agents.profile_dir(tmp_path)}" in argv
    assert "--profile-directory=Default" in argv
    assert not any("Google\\Chrome\\User Data" in item for item in argv)


def test_setup_browser_launch_is_idempotent_when_profile_is_already_open(
    tmp_path: Path, monkeypatch
) -> None:
    profile_arg = f"--user-data-dir={chatgpt_child_agents.profile_dir(tmp_path)}"

    class FakeProcess:
        info = {"pid": 4242, "cmdline": ["chrome.exe", profile_arg]}

    monkeypatch.setattr(
        chatgpt_child_agents.psutil, "process_iter", lambda _attrs: [FakeProcess()]
    )

    def fail_popen(*_args, **_kwargs):
        raise AssertionError("Popen must not run when the dedicated profile is already open")

    monkeypatch.setattr(chatgpt_child_agents.subprocess, "Popen", fail_popen)
    result = chatgpt_child_agents.launch_setup_browser(tmp_path)

    assert result["launched"] is False
    assert result["already_running"] is True
    assert result["pid"] == 4242
    assert result["profile_dir"] == str(chatgpt_child_agents.profile_dir(tmp_path))


def test_worker_pool_defaults_to_offscreen_real_chrome(tmp_path: Path) -> None:
    pool = chatgpt_child_agents.ChatGPTBrowserPool(tmp_path)
    assert pool.headless is False
    assert pool.browser_channel == "chrome"
    assert "--window-position=-32000,-32000" in chatgpt_child_agents.BACKGROUND_BROWSER_ARGS


def test_worker_pool_can_still_request_true_headless(tmp_path: Path) -> None:
    pool = chatgpt_child_agents.ChatGPTBrowserPool(tmp_path, headless=True)
    assert pool.headless is True
