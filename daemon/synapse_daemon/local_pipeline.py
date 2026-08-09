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

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from .local_agent import DEFAULT_CODER_MODEL, generate_code


class RepairAttempt(BaseModel):
    attempt: int
    error: str = ""
    changed: bool = False
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


def _run(path: Path, cwd: Path, timeout: float = 45.0) -> tuple[bool, str]:
    try:
        proc = subprocess.run([sys.executable, path.name], capture_output=True, text=True,
                              timeout=timeout, cwd=str(cwd))
    except subprocess.TimeoutExpired:
        return False, "the code did not finish within 45s (probable infinite loop)"
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
) -> PipelineResult:
    """Generate code for ``spec``, prove it runs, and repair it from real errors.

    ``max_repairs`` can be raised freely: every attempt is local and therefore free. The
    only reason to bound it at all is that a model which has failed four times with the
    same error is not usually one attempt away from success.
    """
    # Injectable so the orchestration can be tested without spawning anything: the logic
    # worth protecting is the generate/test/repair/escalate sequence, not subprocess itself.
    execute = runner or _run
    ws = Path(workspace).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    target = ws / path
    started = time.time()
    result = PipelineResult(spec=spec, path=path, workspace=str(ws), model=coder_model)

    def emit(kind: str, **rest: Any) -> None:
        if on_event:
            on_event({"type": kind, **rest})

    emit("generating", model=coder_model)
    code = await asyncio.to_thread(generate_code, spec, coder_model)
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
    emit("writing_test")
    test_spec = (
        f"{spec}\n\n"
        f"Write a self-contained test for that code. Import from {Path(path).stem} and "
        "assert the behaviour on representative inputs including edge cases. Use plain "
        "asserts, no test framework. Print 'OK' on the last line. Output only the test code."
    )
    test_code = await asyncio.to_thread(generate_code, test_spec, coder_model)
    test_file = ws / "_pipeline_test.py"
    test_file.write_text(test_code, encoding="utf-8")
    result.test_code = test_code

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

        if attempt == max_repairs:
            result.stop_reason = f"still failing after {max_repairs} repair attempts"
            break

        emit("repairing", attempt=attempt + 1, error=error[:300])
        repair_spec = (
            f"This code was written to satisfy the following requirement:\n{spec}\n\n"
            f"Current code:\n```python\n{result.code}\n```\n\n"
            f"Running the tests produced:\n```\n{error}\n```\n\n"
            "Fix the code so it satisfies the requirement and the tests pass. "
            "Output only the corrected code."
        )
        fixed = await asyncio.to_thread(generate_code, repair_spec, coder_model)
        changed = bool(fixed) and not fixed.startswith("ERROR:") and fixed != result.code
        if changed:
            target.write_text(fixed, encoding="utf-8")
            result.code = fixed
        result.attempts.append(RepairAttempt(attempt=attempt + 1, error=error[:600],
                                             changed=changed,
                                             seconds=round(time.time() - t0, 1)))
        if not changed:
            # Producing the same text again means more attempts will not help.
            result.stop_reason = "the model stopped changing the code"
            break

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
