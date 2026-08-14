"""Code-orchestrated local codegen: generate, test, repair, and escalate only when stuck.

This is the shape that measurement selected. On a 6 GB card, wrapping a coding model in an
agent loop driven by a small tool-calling model scores ~33% on trivial tasks; calling the
coding model directly and letting *Python* handle the orchestration scores 100% on the same
tasks (``benchmarks/local-models/SQUAD_REPORT.md``). The small model has to choose a tool,
format the call, relay the spec and interpret the result -- four failure points, none of
them about coding. So none of that is asked of it here.

The economics this is built around: local inference is free and can run all night, while a
frontier model's budget is finite. So the loop grinds locally for as many attempts as it
takes, and a frontier model is invited in **only** when the local loop is genuinely stuck --
and then it receives a compact escalation packet (spec, current code, real error, what was
already tried) rather than the whole history.
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from .local_agent import DEFAULT_CODER_MODEL, generate_code


RESAMPLE_TEMPERATURES = (0.4, 0.8)
"""Temperatures to retry a repair at when the model returns byte-identical code.

Two, escalating. One is often not enough to leave a strong attractor, and past ~0.8 a coding
model starts inventing APIs, which trades a stuck loop for a confidently wrong one.
"""


class RepairAttempt(BaseModel):
    attempt: int
    error: str = ""
    changed: bool = False
    resamples: int = 0
    """How many extra samples this repair needed before the model wrote anything new."""
    started_over: bool = False
    """Whether the loop fell back to asking for a fresh implementation."""
    seconds: float = 0.0


class PipelineResult(BaseModel):
    spec: str
    path: str
    workspace: str
    model: str
    passed: bool = False
    code: str = ""
    test_code: str = ""
    attempts: list[RepairAttempt] = Field(default_factory=list)
    total_seconds: float = 0.0
    stop_reason: str = ""
    needs_escalation: bool = False
    escalation_packet: str = ""
    """Everything a stronger model needs to finish the job, and nothing more.

    Deliberately compact: the point of escalating is to spend as few expensive tokens as
    possible, so it carries the requirement, the current code and the actual error - not a
    transcript of every local attempt.
    """


def error_fingerprint(error: str) -> str:
    """Reduce a traceback to the part identifying *which* failure it is.

    Line numbers, temp paths and object addresses change between attempts even when the
    underlying fault is identical, so comparing raw text would never detect a repeat. The
    final exception line is the stable part, and it is what a human reads first anyway.
    """
    lines = [ln.strip() for ln in (error or "").strip().splitlines() if ln.strip()]
    if not lines:
        return ""

    exception = ""
    index = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if re.match(r"^[A-Za-z_.]*(Error|Exception)\b", lines[i]):
            exception, index = lines[i], i
            break
    if not exception:
        return lines[-1][:300]

    # A bare `AssertionError` says nothing about *which* assertion. Plain asserts without a
    # message are exactly what a small model writes, so every one of its failures used to
    # fingerprint identically - and the loop, seeing "the same error again", declared the
    # model to be circling a problem it could not diagnose and stopped it early. Measured:
    # four consecutive runs of the storage piece stopped that way after 5-8 of 10 allowed
    # repairs, each having reached a *different* assertion.
    #
    # So when the exception carries no detail, fall back to the statement that raised it -
    # the last source line the traceback quoted.
    if ":" not in exception:
        for line in reversed(lines[:index]):
            if line.startswith("File "):
                continue
            exception = f"{exception} at: {line}"
            break

    # Strip the parts that vary run to run so the same fault compares equal.
    return re.sub(r"line \d+|0x[0-9a-fA-F]+|['\"][^'\"]*[/\\][^'\"]*['\"]", "", exception)[:300]


def public_functions(source: str) -> dict[str, tuple[int, int]]:
    """Top-level function names in ``source``, mapped to their (start, end) line numbers."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            out[node.name] = (start, node.end_lineno or node.lineno)
    return out


def failing_function(error: str, known: dict[str, tuple[int, int]]) -> str:
    """Which declared function this failure is about, or "" if it cannot be pinned down.

    Read from the traceback frame first - `in create_user` is unambiguous - and otherwise
    from the assertion text, which the blueprint scenarios deliberately phrase as
    "create_user must RETURN the new user's id". Names are matched against what the module
    actually defines, so a stray word in a message cannot invent a target.
    """
    if not known:
        return ""
    for line in reversed((error or "").splitlines()):
        match = re.search(r"^\s*File .*, line \d+, in (\w+)", line)
        if match and match.group(1) in known:
            return match.group(1)
    mentioned = [name for name in known if re.search(rf"\b{re.escape(name)}\b", error or "")]
    # Exactly one, or it is a guess. Repairing the wrong function is worse than repairing
    # the whole file, because it looks targeted.
    return mentioned[0] if len(mentioned) == 1 else ""


def splice_function(source: str, name: str, replacement: str) -> str:
    """Swap one function definition into ``source``, leaving every other line untouched.

    This is the whole point of a targeted repair. Measured on the storage piece, scenario
    positions ran `[18, 21, 18]`: the model fixed `create_user`, advanced, then broke it
    again, because a repair rewrites the entire file to change one function. Splicing makes
    that regression structurally impossible rather than merely discouraged.

    Returns "" when the replacement cannot be applied, so the caller falls back to a
    whole-file repair rather than writing something it has not understood.
    """
    here = public_functions(source)
    if name not in here:
        return ""
    incoming = public_functions(replacement)
    if name not in incoming:
        return ""

    new_lines = replacement.splitlines()[incoming[name][0] - 1:incoming[name][1]]
    old_start, old_end = here[name]
    lines = source.splitlines()
    spliced = "\n".join(lines[:old_start - 1] + new_lines + lines[old_end:]) + "\n"
    try:
        ast.parse(spliced)
    except SyntaxError:
        return ""
    return spliced


def _ensure_the_test_runs(test_code: str, emit: Callable[..., None]) -> str:
    """Call the test functions the model defined but never invoked.

    Small models routinely emit ``def test_storage(): ... assert ...`` and stop, with even
    the final ``print('OK')`` indented inside the function. Nothing at module level executes,
    so the file exits 0 having asserted nothing, and the piece is recorded as passing.

    This is not hypothetical and it is not rare. It is the mechanism behind the worst false
    pass this project has produced: `passwords` was graded a clean pass in 117 seconds with
    zero repairs while `verify_password` raised ``NameError: name 'hmac' is not defined`` on
    every call. Its generated test did call `verify_password` - inside a function nobody ran.

    Appending the calls is deliberately preferred over rejecting the test. The assertions
    the model wrote are usually reasonable; they were simply never reached.
    """
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return test_code  # a broken test fails the loop honestly and gets repaired

    defined = [node.name for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not defined:
        return test_code

    called = {
        node.value.func.id
        for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    }
    uncalled = [name for name in defined if name not in called]
    # Only functions that take no arguments can be called blind; anything else was probably
    # a helper the test uses on purpose.
    callable_now = [
        node.name for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in uncalled
        and not (node.args.args or node.args.posonlyargs or node.args.kwonlyargs
                 or node.args.vararg or node.args.kwarg)
    ]
    if not callable_now:
        return test_code

    emit("test_never_ran", functions=callable_now)
    return (test_code.rstrip() + "\n\n"
            + "# Added by the pipeline: defined above and never called, so nothing in it\n"
            + "# would have executed and the file would have passed having asserted nothing.\n"
            + "".join(f"{name}()\n" for name in callable_now))


async def _write_model_test(write_code: Callable[..., str], requirement: str, module: str,
                            coder_model: str, emit: Callable[..., None]) -> str:
    """Ask the model for a test of its own code, and make sure it is one.

    Two things it does left to itself, both of which manufacture confidence: paste a copy of
    the implementation into the test file and assert against *that*, and define a test
    function it never calls.
    """
    test_spec = (
        f"{requirement.strip()}\n\n"
        f"Write a test for that code. It MUST begin with `from {module} import *` and test "
        f"the imported functions. Do NOT re-define or re-implement any of the functions in "
        f"the test file - import them. Assert the behaviour on representative inputs "
        f"including edge cases. Use plain asserts, no test framework. Print 'OK' on the last "
        f"line. Output only the test code."
    )
    test_code = await asyncio.to_thread(write_code, test_spec, coder_model)

    if f"from {module} import" not in test_code and f"import {module}" not in test_code:
        emit("test_rejected", reason="the generated test did not import the module")
        test_code = (f"from {module} import *\n\n"
                     + "\n".join(line for line in test_code.splitlines()
                                 if not line.startswith(("def ", "import ", "from ")))
                     + "\nprint('OK')\n")

    return _ensure_the_test_runs(test_code, emit)


def _run(path: Path, cwd: Path, timeout: float = 45.0) -> tuple[bool, str]:
    # Python decides a cached .pyc is current by comparing the source's mtime *in whole
    # seconds* and its size. A repair very often rewrites the module with the same byte
    # length inside the same second - `return 0` to `return 1` is the smallest example - and
    # then the import serves the previous attempt's bytecode. The loop grades code that was
    # never run, blames the fix that had just been written, and repairs its way around a
    # problem that no longer exists. Reproduced directly before fixing.
    shutil.rmtree(cwd / "__pycache__", ignore_errors=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        # -B as well as the variable: the flag stops it writing a new cache, and deleting
        # the directory stops it reading an old one. Either alone leaves the hole open.
        proc = subprocess.run([sys.executable, "-B", path.name], capture_output=True,
                              text=True, timeout=timeout, cwd=str(cwd), env=env)
    except subprocess.TimeoutExpired:
        # Report the timeout that was actually applied. Hardcoding "45s" here meant a
        # caller-supplied budget produced an error message contradicting it, which sends
        # whoever reads it looking for a limit that was never in force.
        return False, (f"the code did not finish within {timeout:g}s "
                       f"(probable infinite loop)")
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    if proc.returncode == 0:
        return True, ""
    return False, (proc.stderr or proc.stdout or "")[-1200:]


async def run_pipeline(
    spec: str,
    *,
    workspace: str | Path,
    path: str = "solution.py",
    coder_model: str = DEFAULT_CODER_MODEL,
    max_repairs: int = 4,
    write_test: bool = True,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    runner: Callable[[Path, Path], tuple[bool, str]] | None = None,
    extra_test: str = "",
    requirement: str = "",
    generate: Callable[..., str] | None = None,
    resample: bool = True,
    targeted: bool = True,
    advisory_model_test: bool = False,
) -> PipelineResult:
    """Generate code for ``spec``, prove it runs, and repair it from real errors.

    ``max_repairs`` can be raised freely: every attempt is local and therefore free. The
    only reason to bound it at all is that a model which has failed four times with the
    same error is not usually one attempt away from success.
    """
    # Injectable so the orchestration can be tested without spawning anything: the logic
    # worth protecting is the generate/test/repair/escalate sequence, not subprocess itself.
    execute = runner or _run

    # Which model or CLI actually writes the code is the *only* thing that differs between
    # tiers of the runtime ladder. Everything downstream - the contract assertions, the
    # blueprint scenario, the repair loop, the honesty about what was verified - is worth
    # exactly as much when Claude wrote the piece as when a 7B did, so it is shared rather
    # than reimplemented per runtime. `generate` defaults to the local coder because that is
    # the tier this loop was built for.
    def _default_generate(*args, **kwargs):
        return generate_code(*args, **kwargs)

    write_code = generate or _default_generate
    ws = Path(workspace).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    target = ws / path
    started = time.time()
    result = PipelineResult(spec=spec, path=path, workspace=str(ws), model=coder_model)

    def emit(kind: str, **rest: Any) -> None:
        if on_event:
            on_event({"type": kind, **rest})

    emit("generating", model=coder_model)
    code = await asyncio.to_thread(write_code, spec, coder_model)
    if code.startswith("ERROR:"):
        result.stop_reason = code
        result.total_seconds = round(time.time() - started, 1)
        return result
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")
    result.code = code
    emit("generated", chars=len(code))

    if not write_test:
        result.passed = True
        result.stop_reason = "generated without verification (write_test disabled)"
        result.total_seconds = round(time.time() - started, 1)
        return result

    # The test is written from the requirement, independently of the implementation, so it
    # encodes what was asked for rather than what the code happens to do.
    #
    # `requirement` rather than `spec`: the codegen spec accumulates implementation aids -
    # the declared contract, the interfaces of every dependency, and an entire worked
    # exemplar page - none of which describe what to *test*. A test prompt carrying a whole
    # exemplar HTML page invites the model to write about the exemplar. Callers that do not
    # separate the two get the old behaviour.
    module = Path(path).stem

    # When the blueprint brought its own acceptance scenario, the model's test is a second
    # opinion rather than the gate - and a frequently wrong one. Measured: it asserted
    # `user_id == 1`, true only of a fresh database, and its message-less `assert x == y`
    # lines collided into a single fingerprint that stopped a progressing loop eight repairs
    # early. Dropping it also saves a whole generation per piece.
    if advisory_model_test and extra_test.strip():
        emit("model_test_skipped", reason="the blueprint scenario is the gate")
        test_code = "print('OK')\n"
    else:
        emit("writing_test")
        test_code = await _write_model_test(
            write_code, requirement or spec, module, coder_model, emit)

    # Contract assertions run *first* in the same file, so a signature mismatch fails the
    # loop and gets repaired locally like any other error. Checking the contract only after
    # the pipeline finished meant the model never saw the problem it could most easily fix -
    # and a module that satisfies its own generated test while exposing the wrong signature
    # to its callers is precisely how two pieces end up disagreeing.
    #
    # The star import has to lead. Blueprint scenarios call the module's functions by bare
    # name, the way a caller does, and the only `from <module> import *` in the file used to
    # be the one inside the *model's* test - appended after. So every scenario died with
    # `NameError: name 'init_db' is not defined` on its first line, in every build, and the
    # failure looked enough like a real one to be mistaken for the model circling a problem
    # it could not diagnose. Not one scenario assertion had ever executed.
    if extra_test:
        test_code = (f"from {module} import *  # noqa: F403 - scenarios call by bare name\n\n"
                     + extra_test.rstrip() + "\n\n" + test_code)

    # Named after the module rather than a fixed `_pipeline_test.py`: several pieces share one
    # workspace, so a single name meant each piece silently erased the evidence for the one
    # before it. When a piece later turned out to have passed on a test that could not
    # possibly have passed, the test that let it through no longer existed to be read.
    test_file = ws / f"_test_{Path(path).stem}.py"
    test_file.write_text(test_code, encoding="utf-8")
    result.test_code = test_code

    seen_errors: set[str] = set()

    circling: str = ""

    for attempt in range(max_repairs + 1):
        emit("testing", attempt=attempt)
        t0 = time.time()
        # Off the event loop: this blocks for as long as the generated code takes to run,
        # and blocking here would freeze every other request the daemon is serving. On
        # Windows it also deadlocks the Proactor loop outright.
        ok, error = await asyncio.to_thread(execute, test_file, ws)
        if ok:
            result.passed = True
            result.stop_reason = "tests passed"
            break

        # Giving up is decided here, *after* testing the repair, rather than at the moment
        # the repeat was detected. Bailing out earlier discarded a fix the model had already
        # written without ever running it - measured: `passwords` ended a build holding
        # correct code, having just added the missing `import hmac`, and was still reported
        # as an escalation because the loop left before testing it. The saving that
        # early-escalation exists for is the *generation* step, and that has already been
        # paid by this point; one more test run costs a second.
        if circling:
            result.stop_reason = circling
            break

        if attempt == max_repairs:
            result.stop_reason = f"still failing after {max_repairs} repair attempts"
            break

        fingerprint = error_fingerprint(error)
        error_repeated = bool(fingerprint) and fingerprint in seen_errors
        seen_errors.add(fingerprint)

        emit("repairing", attempt=attempt + 1, error=error[:300])

        # Always defined: the resample and start-over paths below re-ask this same question,
        # and a targeted repair that does not apply falls back to it.
        repair_spec = (
            f"This code was written to satisfy the following requirement:\n{spec}\n\n"
            f"Current code:\n```python\n{result.code}\n```\n\n"
            f"Running the tests produced:\n```\n{error}\n```\n\n"
            "Fix the code so it satisfies the requirement and the tests pass. "
            "Output only the corrected code."
        )

        # Ask for one function when the failure names one. A whole-file rewrite is how a
        # model fixes `create_user` and breaks `get_user_by_email` in the same breath.
        target_fn = failing_function(error, public_functions(result.code)) if targeted else ""
        spliced = ""
        if target_fn:
            emit("targeted_repair", attempt=attempt + 1, function=target_fn)
            piece_spec = (
                f"This module was written to satisfy:\n{spec}\n\n"
                f"Here is the whole module for context:\n```python\n{result.code}\n```\n\n"
                f"Running the tests produced:\n```\n{error}\n```\n\n"
                f"Rewrite ONLY the function `{target_fn}` so this failure cannot happen. "
                f"Output that one function and nothing else - no imports, no other "
                f"functions, no explanation. Everything else in the module is already "
                f"correct and must not change."
            )
            candidate = await asyncio.to_thread(write_code, piece_spec, coder_model)
            if candidate and not candidate.startswith("ERROR:"):
                spliced = splice_function(result.code, target_fn, candidate)
            if not spliced:
                emit("targeted_repair_fell_back", attempt=attempt + 1, function=target_fn)

        if spliced:
            fixed = spliced
        else:
            fixed = await asyncio.to_thread(write_code, repair_spec, coder_model)

        # Greedy decoding is deterministic, so an unchanged answer to a near-identical
        # prompt is what the sampler is *for*, not evidence the model is out of ideas.
        # Measured: `storage` was reported as "the model stopped changing the code" after
        # two repairs, having never once reached its acceptance scenario - the loop gave up
        # eight attempts early on the strength of a property of temperature 0. Drawing a
        # different sample costs local time, which is free, and is the one thing that can
        # break the tie.
        # Only for a sampler that can actually be turned up. An agentic CLI is already
        # nondeterministic, has no temperature to raise, and bills for every call - so the
        # resample and start-over ladder below would spend real money re-asking a question
        # whose premise (greedy decoding repeats itself) does not apply to it.
        resamples = 0
        while (resample and fixed == result.code and not fixed.startswith("ERROR:")
               and resamples < len(RESAMPLE_TEMPERATURES)):
            temperature = RESAMPLE_TEMPERATURES[resamples]
            resamples += 1
            emit("resampling", attempt=attempt + 1, temperature=temperature)
            fixed = await asyncio.to_thread(write_code, repair_spec, coder_model,
                                            900.0, 8192, temperature)

        # Temperature turned out not to be enough, and the reason is instructive: a repair
        # prompt hands the model the entire current file and asks for a corrected copy, so
        # most of the output is copying. That distribution stays peaked however hot the
        # sampler runs - measured on `storage`, byte-identical ~3.8 KB at 0, 0.4 and 0.8,
        # on a model that demonstrably does vary its output at those temperatures.
        #
        # So stop showing it the thing it keeps copying. This asks for a fresh
        # implementation from the requirement and the failure, with the dead end named but
        # not pasted in. It is the last thing tried before escalating, because a rewrite
        # discards whatever the current attempt already had right.
        started_over = False
        if resample and fixed == result.code and not fixed.startswith("ERROR:"):
            started_over = True
            emit("starting_over", attempt=attempt + 1)
            fixed = await asyncio.to_thread(
                write_code,
                f"Write code satisfying this requirement:\n{spec}\n\n"
                f"A previous attempt failed with:\n```\n{error}\n```\n\n"
                "Do not reproduce that attempt - write the module fresh, and make sure the "
                "failure above cannot happen. Output only the code.",
                coder_model, 900.0, 8192, RESAMPLE_TEMPERATURES[-1])

        changed = bool(fixed) and not fixed.startswith("ERROR:") and fixed != result.code
        if changed:
            target.write_text(fixed, encoding="utf-8")
            result.code = fixed
        result.attempts.append(RepairAttempt(attempt=attempt + 1, error=error[:600],
                                             changed=changed, resamples=resamples,
                                             started_over=started_over,
                                             seconds=round(time.time() - t0, 1)))
        # Two distinct ways of being stuck, reported distinctly because they suggest
        # different fixes. Identical code is checked first: when the model repeats itself the
        # error necessarily repeats too, and "it stopped changing the code" is the root
        # cause, while "the same error came back" would be the symptom.
        if not changed:
            result.stop_reason = (
                f"the model returned identical code across {resamples + 2} samples - "
                f"{resamples} at raised temperature and one asked to start over from the "
                f"requirement alone")
            break
        if error_repeated:
            # It produced *different* code and still hit the same failure - it is circling a
            # problem it does not understand. Measured: a 7B model emitted the identical
            # "module has no attribute user_exists" four times running, costing about twenty
            # minutes to learn what the second attempt had already shown. Recorded rather
            # than acted on, so the repair just written still gets tested at the top of the
            # next pass; if it passes, the model was one attempt from success after all.
            circling = (
                "a different fix produced the same error, so the model is circling a problem "
                f"it cannot diagnose: {fingerprint[:150]}")

    result.total_seconds = round(time.time() - started, 1)

    if not result.passed:
        result.needs_escalation = True
        last_error = result.attempts[-1].error if result.attempts else "no error captured"
        result.escalation_packet = (
            f"A local model could not satisfy this requirement after "
            f"{len(result.attempts)} repair attempts.\n\n"
            f"REQUIREMENT:\n{spec}\n\n"
            f"CURRENT CODE ({path}):\n```python\n{result.code}\n```\n\n"
            f"TEST BEING RUN:\n```python\n{result.test_code[:1500]}\n```\n\n"
            f"LAST ERROR:\n```\n{last_error}\n```\n\n"
            f"Reason it stopped: {result.stop_reason}."
        )
    emit("done", passed=result.passed, seconds=result.total_seconds)
    return result
