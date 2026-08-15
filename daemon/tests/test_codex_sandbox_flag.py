"""Codex must not be launched with a flag that disables the sandbox it was given.

`--ignore-user-config` silently overrides `--sandbox workspace-write` back to read-only -
whatever the flag order, and even against an explicit `-c sandbox_mode="workspace-write"`.
Codex then reports `sandbox: read-only` in its own header, refuses every patch with
"writing is blocked by read-only sandbox", **and exits 0**. The caller sees a success with
an empty workspace.

Measured directly, same directory, same prompt:

    with    --ignore-user-config -> sandbox: read-only,       no file written
    without --ignore-user-config -> sandbox: workspace-write, file written

Found by exercising the codex rung of the ladder for the first time. Until then `claude` had
built every piece, so nothing had ever asked codex to write anything - and the rung that
engages when Claude credits run out was broken in a way that reports success.
"""

from __future__ import annotations

import pytest

from synapse_daemon.agent_squads import AgentExecutionAuthority
from synapse_daemon.coder_runtimes import CoderRuntime, headless_argv


def _argv(runtime: CoderRuntime, authority=AgentExecutionAuthority.WORKSPACE) -> list[str]:
    return headless_argv([runtime.value], runtime=runtime.value, authority=authority,
                         prompt="write the module")


def test_codex_is_not_given_ignore_user_config():
    argv = _argv(CoderRuntime.CODEX)
    assert "--ignore-user-config" not in argv, (
        "this flag forces codex back to a read-only sandbox and it exits 0 anyway, so the "
        "build reports success over an empty workspace")


def test_codex_workspace_authority_actually_asks_for_write():
    argv = _argv(CoderRuntime.CODEX)
    assert "--sandbox" in argv
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"


def test_codex_observe_authority_is_still_read_only():
    """Widening the sandbox for WORKSPACE must not widen it for OBSERVE."""
    argv = _argv(CoderRuntime.CODEX, AgentExecutionAuthority.OBSERVE)
    assert argv[argv.index("--sandbox") + 1] == "read-only"


def test_codex_still_skips_the_git_repo_check():
    """Generated workspaces are not git repos; codex refuses to run in one otherwise."""
    assert "--skip-git-repo-check" in _argv(CoderRuntime.CODEX)


@pytest.mark.parametrize("runtime", [CoderRuntime.CLAUDE, CoderRuntime.COPILOT])
def test_the_other_runtimes_are_unchanged(runtime):
    """The fix is codex-specific; nothing else should have moved."""
    argv = _argv(runtime)
    assert argv[0] == runtime.value
    assert "write the module" in argv


def test_copilots_real_quota_message_reads_as_exhaustion():
    """Verbatim from the first copilot run, which was genuinely out of monthly quota.

    The existing patterns expected "quota exceeded" in that order and matched nothing, so
    an exhausted tier looked like a hard failure - the single distinction the ladder exists
    to make. Caught only because the rung was finally exercised against a real account.
    """
    from synapse_daemon.coder_runtimes import looks_exhausted

    real = ("You have exceeded your monthly quota "
            "(Request ID: E543:175B32:7E5B21:A0C3E4:6A7FD9EE)")
    assert looks_exhausted(real, 1), "a real quota message did not read as exhaustion"


@pytest.mark.parametrize("text,returncode", [
    # Exit 0 is a success; scanning it would demote a healthy paid runtime for the day.
    ("You have exceeded your monthly quota", 0),
    # A build legitimately asked to WRITE rate-limiting code prints these words.
    ('def check_quota(): raise QuotaExceeded("monthly limit")', 1),
    ("SyntaxError: invalid syntax", 1),
])
def test_exhaustion_does_not_fire_on_healthy_or_unrelated_output(text, returncode):
    """A false exhaustion is the expensive direction: it silently drops to the free tier."""
    from synapse_daemon.coder_runtimes import looks_exhausted

    assert not looks_exhausted(text, returncode)
