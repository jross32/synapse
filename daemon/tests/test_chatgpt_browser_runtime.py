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


def test_typed_text_landed_true_for_matching_content():
    assert runtime._typed_text_landed("hello world", "hello world") is True


def test_typed_text_landed_true_for_whitespace_normalized_content():
    """Contenteditable can represent line breaks differently than the source string --
    only real content loss should fail this, not formatting differences."""
    assert runtime._typed_text_landed("line one\nline two", "line one line two") is True


def test_typed_text_landed_false_for_empty_composer():
    """The exact real-world failure this function exists to catch: `type()` reported success
    but the composer is completely empty afterward -- nothing actually landed."""
    assert runtime._typed_text_landed("a real prompt that was typed", "") is False


def test_typed_text_landed_false_for_drastically_truncated_content():
    assert runtime._typed_text_landed("a" * 100, "a" * 10) is False


def test_typed_text_landed_true_for_empty_prompt():
    assert runtime._typed_text_landed("", "") is True


class _FakeLocator:
    def __init__(self, *, count: int = 0, text: str = ""):
        self._count = count
        self._text = text

    async def count(self):
        return self._count

    async def inner_text(self):
        return self._text

    async def click(self):
        pass

    @property
    def first(self):
        return self


class _FakeSendKeyboard:
    def __init__(self, page: "_FakeSendPage"):
        self._page = page

    async def type(self, text):
        self._page.typed.append(text)

    async def press(self, key):
        self._page.keys_pressed.append(key)
        if key == "Enter":
            self._page._sent = True  # noqa: SLF001 - cooperating test double


class _FakeSendPage:
    """Minimal fake driving `_send_and_confirm_started` without a real browser.

    `composer_text_after_type` simulates what actually landed in the composer once
    `_type_multiline` "finishes" (the real bug: this can silently stay empty even though
    typing reported no error). `stop_visible_after_send` simulates whether the stop button
    ever appears once Enter is pressed.
    """

    def __init__(
        self,
        *,
        composer_text_after_type: str,
        stop_visible_after_send: bool,
        length_limit_reached: bool = False,
    ):
        self._composer_text_after_type = composer_text_after_type
        self._stop_visible_after_send = stop_visible_after_send
        self._length_limit_reached = length_limit_reached
        self._sent = False
        self.keys_pressed: list[str] = []
        self.typed: list[str] = []
        self.keyboard = _FakeSendKeyboard(self)

    def locator(self, selector: str):
        if selector == runtime._COMPOSER_SELECTOR:
            if not self._sent:
                return _FakeLocator(text=self._composer_text_after_type)
            # Real ChatGPT clears the composer once a message is accepted.
            return _FakeLocator(text="")
        if selector == runtime._STOP_BUTTON_SELECTOR:
            return _FakeLocator(count=1 if (self._sent and self._stop_visible_after_send) else 0)
        if selector == "body":
            text = (
                "You've reached the maximum length for this conversation, but you can keep "
                "talking by starting a new chat."
                if self._length_limit_reached
                else "ordinary page text with no limit banner"
            )
            return _FakeLocator(text=text)
        raise AssertionError(f"unexpected selector: {selector}")


def test_send_and_confirm_started_succeeds_when_composer_clears_and_stop_appears():
    import asyncio

    page = _FakeSendPage(composer_text_after_type="a real prompt", stop_visible_after_send=True)
    outcome = asyncio.run(runtime._send_and_confirm_started(page, "a real prompt"))

    assert outcome is None
    assert "Enter" in page.keys_pressed


def test_send_and_confirm_started_fails_fast_when_composer_stayed_empty_after_typing():
    """The exact real-world bug: `type()` looked fine but nothing landed. Must be caught
    BEFORE Enter is ever pressed -- never send blindly."""
    import asyncio

    page = _FakeSendPage(composer_text_after_type="", stop_visible_after_send=True)
    outcome = asyncio.run(runtime._send_and_confirm_started(page, "a real prompt"))

    assert outcome is not None
    assert "did not match" in outcome
    assert "Enter" not in page.keys_pressed  # never sent an empty/failed composer


def test_conversation_length_limit_reached_true_when_banner_present():
    import asyncio

    page = _FakeSendPage(
        composer_text_after_type="irrelevant",
        stop_visible_after_send=False,
        length_limit_reached=True,
    )
    assert asyncio.run(runtime.conversation_length_limit_reached(page)) is True


def test_conversation_length_limit_reached_false_for_ordinary_page():
    import asyncio

    page = _FakeSendPage(composer_text_after_type="irrelevant", stop_visible_after_send=False)
    assert asyncio.run(runtime.conversation_length_limit_reached(page)) is False


def test_send_and_confirm_started_fails_fast_on_length_limit_without_typing():
    """A maxed-out conversation is a PERMANENT condition -- must be caught before ever
    attempting to type or press Enter, not discovered later via a composer/stop-button
    mismatch that would misleadingly suggest a transient send failure."""
    import asyncio

    page = _FakeSendPage(
        composer_text_after_type="a real prompt",
        stop_visible_after_send=True,
        length_limit_reached=True,
    )
    outcome = asyncio.run(runtime._send_and_confirm_started(page, "a real prompt"))

    assert outcome is not None
    assert "maximum length" in outcome
    assert "Branch in new chat" in outcome
    assert page.typed == []  # never even attempted to type into a dead conversation
    assert "Enter" not in page.keys_pressed


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



def test_parse_worked_for_seconds_handles_chatgpt_style_duration():
    assert runtime.parse_worked_for_seconds("Worked for 3m 8s") == 188
    assert runtime.parse_worked_for_seconds("Worked for 35m") == 2100
    assert runtime.parse_worked_for_seconds("Worked for 1h 2m 3s") == 3723


def test_parse_worked_for_seconds_prefers_latest_match():
    text = "Worked for 5s\nolder text\nWorked for 2m 1s"
    assert runtime.parse_worked_for_seconds(text) == 121


def test_parse_worked_for_seconds_returns_none_when_ui_has_no_timer():
    assert runtime.parse_worked_for_seconds("Finished successfully.") is None
