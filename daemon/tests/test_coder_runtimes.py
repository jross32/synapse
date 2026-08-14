"""The runtime ladder: use the best available, fall to free only when forced.

Local models are the bottom rung, not the default. Their place is overnight work when the
paid tiers are out of room - so the thing that has to be right here is *when* a tier is
declared out of room, because getting that wrong in the eager direction silently spends the
rest of the day on a worse model.
"""

from __future__ import annotations

import subprocess

import pytest

from synapse_daemon import coder_runtimes as cr
from synapse_daemon.agent_squads import AgentExecutionAuthority


@pytest.fixture(autouse=True)
def _clean_cooldowns():
    cr.clear_exhausted()
    yield
    cr.clear_exhausted()


def test_the_ladder_puts_paid_runtimes_above_the_free_one():
    """The order is the whole policy: local is a fallback, not a default."""
    order = [r.value for r in cr.DEFAULT_LADDER]
    assert order.index("claude") < order.index("local")
    assert order.index("codex") < order.index("local")
    assert order.index("copilot") < order.index("local")
    assert order[-1] == "local", f"local must be last, got {order}"


def test_exhaustion_falls_exactly_one_rung(monkeypatch):
    monkeypatch.setattr(cr, "available", lambda runtime: True)

    assert cr.pick().chosen == "claude"

    cr.mark_exhausted(cr.CoderRuntime.CLAUDE)
    decision = cr.pick()
    assert decision.chosen == "codex", decision.describe()
    assert decision.skipped == ["claude"]
    assert "out of room" in decision.reasons["claude"]

    cr.mark_exhausted(cr.CoderRuntime.CODEX)
    cr.mark_exhausted(cr.CoderRuntime.COPILOT)
    assert cr.pick().chosen == "local", "local is the floor, it must always be reachable"


def test_a_cooldown_expires(monkeypatch):
    monkeypatch.setattr(cr, "available", lambda runtime: True)
    cr.mark_exhausted(cr.CoderRuntime.CLAUDE, seconds=0.01)
    assert cr.pick().chosen == "codex"

    import time

    time.sleep(0.05)
    assert cr.pick().chosen == "claude", "an expired cooldown must release the runtime"


def test_a_runtime_that_is_not_installed_is_skipped_with_a_reason(monkeypatch):
    monkeypatch.setattr(cr, "available",
                        lambda runtime: runtime is not cr.CoderRuntime.CLAUDE)
    decision = cr.pick()
    assert decision.chosen == "codex"
    assert decision.reasons["claude"] == "not installed"
    assert "codex" in decision.describe()


# --- exhaustion detection ---------------------------------------------------------------
# The eager direction is the expensive one: a false positive demotes a paid runtime to the
# free tier for an hour, on every build, and nothing announces it.

@pytest.mark.parametrize("line", [
    "Error: usage limit reached. Try again at 3pm.",
    "API error: 429 Too Many Requests",
    "quota exceeded for this organization",
    "Your credit balance is too low to continue",
    "insufficient_quota",
])
def test_real_exhaustion_is_detected(line):
    assert cr.looks_exhausted(line, 1), f"missed a real exhaustion: {line!r}"


@pytest.mark.parametrize("text,code", [
    ("Error: usage limit reached", 0),          # succeeded - not exhausted, whatever it said
    ("wrote a rate limiter to api.py", 1),      # the model was asked to build one
    ("done: implemented rate_limit(requests)", 1),
    ('Traceback (most recent call last):\n  File "x.py", line 3\nKeyError: rate_limit', 1),
    ("", 1),
    ("SyntaxError: invalid syntax", 1),
    ("  File \"api.py\", line 429, in handler", 1),   # a line number, not a status code
    ("429 tests passed", 1),
    ("AssertionError: expected rate_limit to be called", 1),
])
def test_healthy_output_is_never_read_as_exhaustion(text, code):
    assert cr.looks_exhausted(text, code) == "", (
        f"a working runtime would have been demoted by: {text!r}")


# --- headless invocation ------------------------------------------------------------------

@pytest.mark.parametrize("runtime,expected", [
    ("claude", "--print"),
    ("codex", "exec"),
    ("copilot", "--no-ask-user"),
    ("gemini", "--prompt"),
])
def test_each_runtime_gets_its_own_headless_flag(runtime, expected):
    """Without these the CLI opens interactively and a headless build hangs forever."""
    argv = cr.headless_argv([runtime], runtime=runtime,
                            authority=AgentExecutionAuthority.WORKSPACE, prompt="hi")
    assert expected in argv, f"{runtime} was not invoked headlessly: {argv}"
    assert "hi" in argv[-1]


def test_an_unknown_runtime_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        cr.headless_argv(["nope"], runtime="nope",
                         authority=AgentExecutionAuthority.WORKSPACE, prompt="x")


def test_a_runtime_that_writes_nothing_is_not_believed(tmp_path, monkeypatch):
    """An agent reporting success without producing the file must fail, not pass."""
    monkeypatch.setattr(cr, "resolve_command", lambda name: "fake-cli")
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "done!", ""))

    result = cr.write_module(cr.CoderRuntime.CLAUDE, "make it", workspace=tmp_path,
                             path="thing.py")
    assert not result.ok
    assert "without writing thing.py" in result.error


def test_the_written_file_is_read_back_from_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "resolve_command", lambda name: "fake-cli")

    def fake_run(argv, **kwargs):
        (tmp_path / "thing.py").write_text("VALUE = 41\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = cr.write_module(cr.CoderRuntime.CODEX, "make it", workspace=tmp_path,
                             path="thing.py")
    assert result.ok
    assert result.source == "VALUE = 41\n"


def test_exhaustion_during_a_write_is_surfaced_not_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "resolve_command", lambda name: "fake-cli")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 1, "", "Error: usage limit reached"))

    result = cr.write_module(cr.CoderRuntime.CLAUDE, "make it", workspace=tmp_path,
                             path="thing.py")
    assert not result.ok
    assert result.exhausted, "the caller cannot fall down the ladder without this"
    assert "usage limit reached" in result.exhausted


def test_a_module_written_under_the_agents_own_name_is_adopted(tmp_path, monkeypatch):
    """Measured against the real CLI: asked for `slug.py`, Claude wrote `slugify.py`.

    It named the file after the function and exited 0, having done good work in the wrong
    place. One unambiguous new module is a misfiling, not a failure.
    """
    monkeypatch.setattr(cr, "resolve_command", lambda name: "fake-cli")

    def fake_run(argv, **kwargs):
        (tmp_path / "slugify.py").write_text("def slugify(t):\n    return t\n",
                                             encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = cr.write_module(cr.CoderRuntime.CLAUDE, "make a slugifier",
                             workspace=tmp_path, path="slug.py")

    assert result.ok
    assert result.renamed_from == "slugify.py", "the adoption was not recorded"
    assert (tmp_path / "slug.py").exists()
    assert not (tmp_path / "slugify.py").exists()


def test_several_new_modules_are_reported_rather_than_guessed_between(tmp_path, monkeypatch):
    """Adopting one of them would be picking a file at random and calling it the answer."""
    monkeypatch.setattr(cr, "resolve_command", lambda name: "fake-cli")

    def fake_run(argv, **kwargs):
        (tmp_path / "slugify.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "helpers.py").write_text("y = 2\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = cr.write_module(cr.CoderRuntime.CLAUDE, "make it", workspace=tmp_path,
                             path="slug.py")

    assert not result.ok
    assert "helpers.py" in result.error and "slugify.py" in result.error


def test_the_requested_filename_leads_the_prompt(tmp_path, monkeypatch):
    """The instruction trailing the requirement is what got ignored in the real run."""
    monkeypatch.setattr(cr, "resolve_command", lambda name: "fake-cli")
    seen: dict[str, str] = {}

    def fake_run(argv, **kwargs):
        seen["prompt"] = argv[-1]
        (tmp_path / "slug.py").write_text("x = 1\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    cr.write_module(cr.CoderRuntime.CLAUDE, "REQUIREMENT-TEXT", workspace=tmp_path,
                    path="slug.py")

    prompt = seen["prompt"]
    assert prompt.index("slug.py") < prompt.index("REQUIREMENT-TEXT"), (
        f"the filename must lead, or it gets ignored:\n{prompt[:200]}")


def test_an_unchanged_file_is_not_counted_as_written(tmp_path, monkeypatch):
    """A CLI that runs, succeeds and edits nothing has not done the work."""
    (tmp_path / "thing.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(cr, "resolve_command", lambda name: "fake-cli")
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))

    result = cr.write_module(cr.CoderRuntime.COPILOT, "make it", workspace=tmp_path,
                             path="thing.py")
    assert not result.ok
    assert "unchanged" in result.error
