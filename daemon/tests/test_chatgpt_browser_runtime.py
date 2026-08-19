"""Tests for the ChatGPT-web coder runtime -- the browser-driven rung, not a CLI subprocess.

No real browser or network here: these prove the graceful-failure paths (missing profile,
missing playwright dependency) and the ladder-exclusion decision, all of which are
deterministic without ever launching Chromium. Actually driving a live chatgpt.com tab needs
a real, human-logged-in profile and is exercised by hand, not by this suite -- same reasoning
scaffold/webcheck.py's tests use for its own browser checks.
"""

from __future__ import annotations

from synapse_daemon import chatgpt_browser_runtime as runtime
from synapse_daemon import coder_runtimes


def test_profile_available_false_for_missing_directory(tmp_path):
    assert runtime.profile_available(tmp_path / "does-not-exist") is False


def test_profile_available_false_for_empty_directory(tmp_path):
    empty = tmp_path / "empty-profile"
    empty.mkdir()
    assert runtime.profile_available(empty) is False


def test_profile_available_true_once_something_is_in_it(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "Default").mkdir()
    assert runtime.profile_available(profile) is True


def test_run_prompt_reports_missing_profile_without_touching_a_browser(tmp_path):
    """The most common real-world state: no one has logged in yet. This must come back as an
    ordinary RuntimeResult.error, never raise, and never attempt to launch Playwright."""
    result = runtime.run_prompt_sync(
        "irrelevant prompt", profile_dir=tmp_path / "never-logged-in")

    assert result.ok is False
    assert result.runtime == "chatgpt_web"
    assert "one-time human login" in result.error
    assert result.seconds >= 0


def test_chatgpt_web_is_a_real_runtime_but_excluded_from_the_default_ladder():
    """Deliberate, not an oversight: CHATGPT_WEB exists as a runtime identity so results/logs
    can name it consistently, but coder_runtimes.pick() must never auto-select it until it's
    been proven live -- see both modules' docstrings for why. This test exists so a future
    edit that casually adds it to DEFAULT_LADDER has to consciously break this assertion."""
    assert coder_runtimes.CoderRuntime.CHATGPT_WEB.value == "chatgpt_web"
    assert coder_runtimes.CoderRuntime.CHATGPT_WEB not in coder_runtimes.DEFAULT_LADDER


def test_type_multiline_splits_on_shift_enter_not_enter():
    """The load-bearing fix this module exists for: a literal newline must never become a
    bare Enter (which sends prematurely in the real UI), only Shift+Enter (which does not)."""
    import asyncio

    keys_pressed: list[str] = []
    typed: list[str] = []

    class FakeKeyboard:
        async def type(self, text):
            typed.append(text)

        async def press(self, key):
            keys_pressed.append(key)

    class FakePage:
        keyboard = FakeKeyboard()

    asyncio.run(runtime._type_multiline(FakePage(), "line one\nline two\nline three"))

    assert typed == ["line one", "line two", "line three"]
    # Exactly two line breaks for three lines, all Shift+Enter -- never a bare Enter, which
    # is the premature-send bug this module exists to avoid. Sending is the caller's job,
    # done exactly once, after typing is fully complete.
    assert keys_pressed == ["Shift+Enter", "Shift+Enter"]
