"""One place that knows how to run a coding CLI headlessly, and whether it can be run now.

Synapse can reach several coding runtimes: the Claude, Codex, Copilot and Gemini CLIs, and
the local Ollama models. They are not interchangeable in quality or in price, and the order
that matters to the person paying is:

    claude -> codex -> copilot -> local

Paid runtimes first while their credits last; the local models are the tier you fall to when
everything above is exhausted, and they are suited to overnight work rather than to waiting
on. This module answers the two questions a build needs: *which tier can I use right now*,
and *how do I actually invoke it without a human in the loop*.

The headless invocations here were already proven in `routes_agent_squads`, which spawns
automatic workers with them. They are lifted rather than rewritten, and that module now
calls this one, so a flag learned the hard way is not learned twice.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from .agent_squads import AgentExecutionAuthority
from .runtime_resolution import resolve_command


class CoderRuntime(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"
    COPILOT = "copilot"
    GEMINI = "gemini"
    LOCAL = "local"


DEFAULT_LADDER: tuple[CoderRuntime, ...] = (
    CoderRuntime.CLAUDE,
    CoderRuntime.CODEX,
    CoderRuntime.COPILOT,
    CoderRuntime.GEMINI,
    CoderRuntime.LOCAL,
)
"""Best first, free last.

Gemini sits below the paid trio and above the local models on purpose. It is not as strong
as Claude or Codex on this kind of work, so it is a *last paid resort* rather than a
preference - but it is a far better place to land than the local tier, because it answers in
minutes rather than overnight and its free allowance is generous where Copilot's is not.

Verified on this machine before being added: it built the `reader` piece 1/1, verified, zero
repairs, 188 s. That check exists because the two rungs before it, `codex` and `copilot`,
had both never been exercised and both turned out to be broken - one silently writing
nothing and exiting 0.

Google's free allowance is per-model and the difference is large: Flash and Flash-Lite get
~1,500 requests/day, while Pro is 25-50/day and, since May 2026, largely behind billing. So
a Gemini rung should ask for a Flash model unless a caller deliberately says otherwise -
picking Pro by default would exhaust the tier in an afternoon.
"""


class RuntimeExhausted(RuntimeError):
    """This tier is out of room. Not a bad answer - a tier that must stop being used.

    Distinguished from an ordinary failure because the responses are opposite: a bad answer
    is worth repairing on the same runtime, while an exhausted account will refuse every
    subsequent call identically until its window resets.
    """

    def __init__(self, runtime: "CoderRuntime", detail: str) -> None:
        super().__init__(f"{runtime.value} is out of room: {detail}")
        self.runtime = runtime
        self.detail = detail


CLAUDE_OBSERVE_DENIED_TOOLS = "Write Edit NotebookEdit"
"""Space separated, which is the form the squad workers have actually been running with.

Claude has no read-only sandbox flag, so unlike Codex's `--sandbox read-only` this is a
policy boundary rather than an enforced one.
"""


@dataclass(frozen=True)
class RuntimeProfile:
    """How hard a rung should try, and what it may spend doing it.

    Every one of these CLIs picks a default when told nothing, and the defaults are not
    what a build wants:

    * **codex** runs at ``reasoning effort: low`` unless told otherwise - measured, its own
      header prints it. A build was getting the cheapest thinking available by accident.
    * **gemini** free allowance is per-model and lopsided: Flash and Flash-Lite get ~1,500
      requests/day while Pro gets 25-50 and is largely behind billing since May 2026. Left
      to a default, a Gemini rung can exhaust the tier in an afternoon.

    So the profile is explicit, per rung, rather than inherited from whatever each vendor
    happens to prefer this month.
    """

    model: str = ""
    effort: str = ""
    """low | medium | high | xhigh | max, mapped onto whatever each CLI calls it."""
    max_budget_usd: float | None = None
    max_credits: int | None = None


# Effort names differ per vendor. Claude takes all five; codex takes three, so the two
# highest collapse onto `high` rather than being dropped silently - asking for `max` and
# getting the default would be the worst outcome.
_CODEX_EFFORT = {"low": "low", "medium": "medium", "high": "high",
                 "xhigh": "high", "max": "high"}

DEFAULT_PROFILES: dict[CoderRuntime, RuntimeProfile] = {
    # Flash by name, because the free allowance depends on it. The CLI resolves the family
    # forward on its own - asking for `gemini-2.5-flash` was served by `gemini-3.5-flash`.
    CoderRuntime.GEMINI: RuntimeProfile(model="gemini-2.5-flash"),
    # Writing a module to a contract is not a task to think about as little as possible.
    CoderRuntime.CODEX: RuntimeProfile(effort="medium"),
}


def profile_for(runtime: CoderRuntime,
                override: RuntimeProfile | None = None) -> RuntimeProfile:
    """The profile a rung runs under: the caller's if given, else this rung's default."""
    return override or DEFAULT_PROFILES.get(runtime, RuntimeProfile())


def headless_argv(
    argv: list[str],
    *,
    runtime: str,
    authority: AgentExecutionAuthority,
    prompt: str,
    profile: RuntimeProfile | None = None,
) -> list[str]:
    """Translate one headless launch into each supported CLI.

    Interactive is every one of these CLIs' default. Each branch below names the flag that
    makes it execute a prompt and exit, plus the flags that bound what it may touch.
    """
    executable, *runtime_args = argv
    profile = profile or DEFAULT_PROFILES.get(CoderRuntime(runtime), RuntimeProfile())
    if runtime == CoderRuntime.CLAUDE.value:
        permission_args = {
            # `plan` is structurally wrong for a headless worker: its purpose is to withhold
            # action until a human approves, and nobody is there to approve. `auto` is the
            # non-interactive path; read-only intent is carried by denying the mutating
            # tools rather than by a mode that also denies finishing.
            AgentExecutionAuthority.OBSERVE: [
                "--permission-mode", "auto",
                "--disallowedTools", CLAUDE_OBSERVE_DENIED_TOOLS,
            ],
            AgentExecutionAuthority.WORKSPACE: ["--permission-mode", "auto"],
            AgentExecutionAuthority.FULL: ["--dangerously-skip-permissions"],
        }[authority]
        tuning: list[str] = []
        if profile.model:
            tuning += ["--model", profile.model]
        if profile.effort:
            tuning += ["--effort", profile.effort]
        if profile.max_budget_usd is not None:
            # A ceiling the CLI enforces itself, so a runaway loop cannot outspend it even
            # if our own accounting is wrong.
            tuning += ["--max-budget-usd", str(profile.max_budget_usd)]
        return [executable, *runtime_args, "--strict-mcp-config", *permission_args,
                *tuning, "--print", prompt]

    if runtime == CoderRuntime.CODEX.value:
        permission_args = {
            AgentExecutionAuthority.OBSERVE: ["--sandbox", "read-only"],
            AgentExecutionAuthority.WORKSPACE: ["--sandbox", "workspace-write"],
            AgentExecutionAuthority.FULL: [
                "--dangerously-bypass-approvals-and-sandbox", "--ignore-rules",
            ],
        }[authority]
        # `--ignore-user-config` is deliberately NOT passed. It silently overrides
        # `--sandbox workspace-write` back to read-only, whatever the flag order and even
        # against an explicit `-c sandbox_mode="workspace-write"`. Codex then reports
        # `sandbox: read-only` in its own header, refuses every patch with
        # "writing is blocked by read-only sandbox", **and exits 0** - so the caller sees a
        # success with an empty workspace rather than an error.
        #
        # Measured directly, same directory, same prompt:
        #   with    --ignore-user-config -> sandbox: read-only,      no file written
        #   without --ignore-user-config -> sandbox: workspace-write, file written
        #
        # The cost of dropping it is that the user's ~/.codex config applies. That is the
        # better trade: a flag that quietly disables the sandbox the caller asked for is
        # worse than a config the user chose on purpose.
        tuning = []
        if profile.model:
            tuning += ["-m", profile.model]
        if profile.effort:
            # Verified against codex's own header, which prints `reasoning effort:` on every
            # run: default `low`, and `-c model_reasoning_effort="high"` moves it to `high`.
            tuning += ["-c", f'model_reasoning_effort="{_CODEX_EFFORT[profile.effort]}"']
        return [executable, "exec", "--skip-git-repo-check",
                "--color", "never", *permission_args, *tuning, *runtime_args, prompt]

    if runtime == CoderRuntime.COPILOT.value:
        permission_args = {
            AgentExecutionAuthority.OBSERVE: ["--deny-tool=write", "--deny-tool=shell"],
            AgentExecutionAuthority.WORKSPACE: ["--allow-all-tools"],
            AgentExecutionAuthority.FULL: ["--allow-all"],
        }[authority]
        tuning = []
        if profile.model:
            tuning += ["--model", profile.model]
        if profile.max_credits is not None:
            tuning += ["--max-ai-credits", str(profile.max_credits)]
        # Copilot exposes no effort control; asking for one is silently ignored rather than
        # faked, because a profile that claims to have raised effort and did not is worse
        # than one that never claimed it.
        return [executable, *runtime_args, "--disable-builtin-mcps", "--no-ask-user",
                *permission_args, *tuning, "--prompt", prompt]

    if runtime == CoderRuntime.GEMINI.value:
        permission_args = {
            AgentExecutionAuthority.OBSERVE: ["--approval-mode", "plan"],
            AgentExecutionAuthority.WORKSPACE: ["--approval-mode", "auto_edit"],
            AgentExecutionAuthority.FULL: ["--approval-mode", "yolo"],
        }[authority]
        tuning = ["-m", profile.model] if profile.model else []
        # `-o json` always: it is the only way to get this rung's token counts back, and the
        # response text is still there under `response`.
        return [executable, *runtime_args, *permission_args, *tuning,
                "-o", "json", "--prompt", prompt]

    raise ValueError(f"no headless invocation known for runtime {runtime!r}")


# Phrases a CLI emits when the account is out of room, not when the code is wrong.
EXHAUSTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I) for p in (
        r"\busage limit reached\b",
        # Space or hyphen only. A CLI reporting a limit writes English ("rate limit"); an
        # underscore means it is an identifier, and `KeyError: rate_limit` in a crashing
        # build would otherwise demote the runtime for an hour.
        r"\brate[ -]?limit(ed|s)?\b",
        r"\bquota (exceeded|exhausted)\b",
        # GitHub Copilot's real wording, caught the first time the rung was exercised:
        # "You have exceeded your monthly quota (Request ID: ...)", exit 1. The patterns
        # above expect "quota exceeded" in that order and matched nothing, so an exhausted
        # tier read as a hard failure - the one thing the ladder exists to tell apart.
        r"\bexceeded your\b.*\b(quota|limit|allowance)\b",
        r"\b(monthly|daily|weekly) (quota|limit|allowance)\b.*\bexceed",
        r"\binsufficient[_ ]quota\b",
        r"\bout of (credits?|tokens?)\b",
        r"\bcredit balance is too low\b",
        r"\btoo many requests\b",
        # Not "line 429" and not "429 tests passed" - only a status code being reported.
        r"(?<!line )\b(http[ /]?)?429\b(?!\s*(tests|files|lines|ms|s\b))",
        r"\bplease (try again|upgrade)\b.*\blimit\b",
        r"\bbilling\b.*\b(required|issue)\b",
    )
)


def looks_exhausted(stderr: str, returncode: int) -> str:
    """The line proving this runtime is out of room, or "" if it is not.

    Only consulted on a **failed** invocation. A build prompt can legitimately ask a model
    to *write* rate-limiting code, and its transcript would then be full of these phrases -
    scanning successful output would demote a perfectly healthy paid runtime to the free
    tier and quietly cost quality for the rest of the day. A false exhaustion is the
    expensive direction here, so the check is deliberately narrow.
    """
    if returncode == 0:
        return ""
    for line in (stderr or "").splitlines():
        # Skip anything that is part of a Python traceback the runtime happened to print.
        # A build that crashes inside a function called `rate_limit` would otherwise be read
        # as the account being out of credit, and the tier would be demoted for an hour on
        # the strength of a variable name.
        if line.startswith((" ", "\t")) or "Traceback" in line or 'File "' in line:
            continue
        for pattern in EXHAUSTION_PATTERNS:
            if pattern.search(line):
                return line.strip()[:300]
    return ""


class RuntimeResult(BaseModel):
    runtime: str
    ok: bool = False
    source: str = ""
    error: str = ""
    exhausted: str = ""
    """The matched line when the runtime reported being out of room. Empty otherwise."""
    renamed_from: str = ""
    """Set when the runtime wrote the module under a name of its own choosing.

    Kept rather than hidden: it is the difference between "the agent did the work" and "the
    harness quietly moved a file", and if it starts happening on every run that is a prompt
    problem worth seeing.
    """
    seconds: float = 0.0


def available(runtime: CoderRuntime) -> bool:
    """Whether this runtime's binary can be found at all.

    Being installed is not the same as having credit. Exhaustion is discovered by running
    it, because no CLI reports remaining quota without being asked to do work.
    """
    if runtime is CoderRuntime.LOCAL:
        return True  # ollama reachability is the local pipeline's own concern
    return resolve_command(runtime.value) is not None


def write_module(
    runtime: CoderRuntime,
    prompt: str,
    *,
    workspace: Path,
    path: str,
    timeout: float = 900.0,
    authority: AgentExecutionAuthority = AgentExecutionAuthority.WORKSPACE,
) -> RuntimeResult:
    """Have a CLI runtime write one module, and return what it wrote.

    These runtimes are agents with filesystem access, so they are asked to *write the file*
    rather than to print source to stdout - printing invites prose, fences and commentary
    around the code, and every one of them writes files natively. The file is then read back
    from disk, which also means an agent that claims success without writing anything is
    caught rather than believed.
    """
    started = time.time()
    result = RuntimeResult(runtime=runtime.value)
    binary = resolve_command(runtime.value)
    if not binary:
        result.error = f"{runtime.value} is not installed on this host"
        return result

    target = Path(workspace) / path
    before = target.read_text(encoding="utf-8") if target.exists() else None
    existing = {p.name for p in Path(workspace).glob("*.py")}

    # The requirement goes in a FILE and the argument stays one line.
    #
    # `claude` resolves to `claude.CMD` on Windows, and cmd.exe treats a newline inside an
    # argument as a command separator - so a multi-line prompt arrives truncated at the
    # first line. Proven directly: a .cmd echoing its first argument printed
    # `GOT:[LINE-ONE]` and dropped the rest. Every multi-line prompt sent this way reached
    # the model as its opening sentence and nothing else, which produced modules built from
    # the *filename* alone: asked for a CSV summariser in `summary.py`, Claude wrote a file
    # containing `# summary.py`.
    #
    # This is the pattern `routes_agent_squads` already uses for exactly the same reason.
    brief = Path(workspace) / f".synapse-brief-{Path(path).stem}.md"
    brief.write_text(
        f"# Write `{path}`\n\n"
        f"Create exactly one file, named `{path}`, in this directory. Do not create any "
        f"other file and do not choose a different name.\n\n{prompt}\n",
        encoding="utf-8")

    argv = headless_argv(
        [binary], runtime=runtime.value, authority=authority,
        prompt=(f"Read the complete instructions in {brief} and carry them out now. "
                f"Write exactly one file, named {path}, in that same directory. "
                f"Do not ask any questions and do not wait for further input."))
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              cwd=str(workspace))
    except subprocess.TimeoutExpired:
        result.error = f"{runtime.value} did not finish within {timeout:g}s"
        result.seconds = round(time.time() - started, 1)
        return result
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
        result.seconds = round(time.time() - started, 1)
        return result

    result.seconds = round(time.time() - started, 1)
    result.exhausted = looks_exhausted(proc.stderr or "", proc.returncode)
    if result.exhausted:
        result.error = f"{runtime.value} is out of room: {result.exhausted}"
        return result

    if not target.exists():
        # An agent that did the work under a name of its own choosing has not failed, it has
        # misfiled. Adopt the file when there is exactly one new module and no ambiguity
        # about which it is; anything else is reported rather than guessed at.
        brief.unlink(missing_ok=True)
        created = [p for p in Path(workspace).glob("*.py") if p.name not in existing]
        if len(created) == 1:
            created[0].replace(target)
            result.renamed_from = created[0].name
        else:
            result.error = (
                f"{runtime.value} exited {proc.returncode} without writing {path}"
                + (f" (it created {sorted(p.name for p in created)})" if created else "")
                + f". {(proc.stderr or proc.stdout or '')[-300:]}")
            return result

    brief.unlink(missing_ok=True)
    source = target.read_text(encoding="utf-8")
    if before is not None and source == before:
        result.error = f"{runtime.value} left {path} unchanged"
        return result

    result.ok = True
    result.source = source
    return result


_EXHAUSTED_UNTIL: dict[str, float] = {}
"""Runtime -> monotonic deadline before which it is not worth asking again.

In memory rather than persisted: a restart should re-probe rather than inherit a stale
belief that a tier is dead. Being wrong in that direction costs one failed call; being wrong
the other way costs every build until someone notices.
"""

DEFAULT_COOLDOWN_SECONDS = 60 * 60
"""One hour. Long enough not to hammer an exhausted account, short enough that a limit which
resets on a rolling window is picked up the same session."""


def mark_exhausted(runtime: CoderRuntime, *, seconds: float = DEFAULT_COOLDOWN_SECONDS) -> None:
    _EXHAUSTED_UNTIL[runtime.value] = time.monotonic() + seconds


def clear_exhausted(runtime: CoderRuntime | None = None) -> None:
    if runtime is None:
        _EXHAUSTED_UNTIL.clear()
    else:
        _EXHAUSTED_UNTIL.pop(runtime.value, None)


def cooling_down(runtime: CoderRuntime) -> float:
    """Seconds left on this runtime's cooldown, 0 if it is usable."""
    deadline = _EXHAUSTED_UNTIL.get(runtime.value)
    if deadline is None:
        return 0.0
    left = deadline - time.monotonic()
    if left <= 0:
        _EXHAUSTED_UNTIL.pop(runtime.value, None)
        return 0.0
    return left


def pick(ladder: tuple[CoderRuntime, ...] = DEFAULT_LADDER) -> LadderDecision:
    """The best runtime usable right now, and why the ones above it were passed over."""
    decision = LadderDecision()
    for runtime in ladder:
        left = cooling_down(runtime)
        if left:
            decision.skipped.append(runtime.value)
            decision.reasons[runtime.value] = f"out of room, retrying in {left / 60:.0f}m"
            continue
        if not available(runtime):
            decision.skipped.append(runtime.value)
            decision.reasons[runtime.value] = "not installed"
            continue
        decision.chosen = runtime.value
        return decision
    return decision


class LadderDecision(BaseModel):
    """Which runtime a piece was built with, and what was skipped to get there."""

    chosen: str = ""
    skipped: list[str] = Field(default_factory=list)
    reasons: dict[str, str] = Field(default_factory=dict)

    def describe(self) -> str:
        if not self.chosen:
            return "no runtime available: " + "; ".join(
                f"{k}: {v}" for k, v in self.reasons.items())
        if not self.skipped:
            return f"built with {self.chosen}"
        return (f"built with {self.chosen}, after "
                + ", ".join(f"{r} ({self.reasons.get(r, 'unavailable')})"
                            for r in self.skipped))
