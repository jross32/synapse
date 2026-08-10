"""Pick the right local strategy and model for a task, in code rather than by asking a model.

The measurement this is built on: small models are reliable at *doing* a narrow job and
unreliable at *choosing* one. Wrapped in an agent loop that has to select a tool, a coding
model scored 33% on tasks it solves 100% of the time when handed the job directly. So the
choosing happens here, in ordinary Python, and the model only ever receives work it is
measured to be good at.

That makes "use the local models" a single call. A caller - a frontier model trying to
conserve its budget, or the UI - posts a task and gets back either a finished result or an
honest "this needs you", without having to know that code should go through the pipeline,
that file work needs an agent, or which of thirteen installed models is the right one.

Routing is deliberately conservative. When a task looks like it needs judgement rather than
verification, it is not attempted locally at all: a wrong answer that reads as confident is
far more expensive than an honest refusal, because the caller then has to detect the error
before they can fix it.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import local_models
from .local_agent import DEFAULT_CODER_MODEL, PermissionMode, run_agent
from .local_pipeline import PipelineResult, run_pipeline


class Strategy(str, Enum):
    PIPELINE = "pipeline"
    """Write code: generate, test, repair. Measured 100% where an agent loop scored 33%."""

    AGENT = "agent"
    """Touch the filesystem: read, summarise, rename, mechanical edits."""

    COMPLETION = "completion"
    """One-shot text work with no tools and no files."""

    ESCALATE = "escalate"
    """Needs judgement rather than verification. Don't guess with a small model."""


class RouteDecision(BaseModel):
    strategy: Strategy
    model: str = ""
    reason: str = ""
    matched: str = ""
    """The signal that decided it, so a surprising route can be explained rather than argued with."""


class RoutedResult(BaseModel):
    task: str
    decision: RouteDecision
    completed: bool = False
    output: str = ""
    pipeline: PipelineResult | None = None
    needs_escalation: bool = False
    escalation_packet: str = ""
    seconds: float = 0.0


# Judgement work: no amount of local repair makes a small model's architectural opinion
# trustworthy, and unlike code there is no test that can prove it wrong. Checked first, so
# "review the security of this design" never gets mistaken for a coding task.
_JUDGEMENT = re.compile(
    r"\b(should we|trade[- ]?off|architect|design (a|the|an)\b|security review|threat model|"
    r"is it (safe|wise|better)|recommend(ation)?|strategy|pros and cons|evaluate whether|"
    r"decide (if|whether)|best approach|opinion)\b", re.I)

_WRITE_CODE = re.compile(
    r"\b(write|implement|create|add|build|generate)\b.{0,40}\b"
    r"(function|class|script|module|endpoint|parser|test|program|cli)\b|"
    r"\bfix\b.{0,30}\b(bug|function|code|error|test)\b|\brefactor\b", re.I)

_FILE_WORK = re.compile(
    r"\b(read|open|list|summari[sz]e|rename|move|delete|search|grep|find)\b.{0,30}"
    r"\b(file|files|folder|directory|repo|codebase|log|logs)\b|"
    r"\bwhat('s| is) in\b|\bwhich files\b", re.I)

_CODE_FILE_HINT = re.compile(r"\.(py|js|ts|tsx|jsx|go|rs|java|rb|sh|sql)\b", re.I)


def route(task: str) -> RouteDecision:
    """Decide how to run ``task`` locally, or that it should not be run locally at all.

    Model choice comes from the testbench sweep, so the coder seat gets whichever model
    actually scored highest at coding on *this* machine rather than whichever is largest.
    """
    text = task.strip()

    judgement = _JUDGEMENT.search(text)
    if judgement:
        return RouteDecision(
            strategy=Strategy.ESCALATE,
            reason=("This asks for judgement, and a local model's answer could not be "
                    "verified by running it. A confident wrong answer costs more than no "
                    "answer, because you have to notice it first."),
            matched=judgement.group(0))

    code = _WRITE_CODE.search(text) or _CODE_FILE_HINT.search(text)
    if code:
        return RouteDecision(
            strategy=Strategy.PIPELINE,
            model=local_models.best_model_for("coding", DEFAULT_CODER_MODEL),
            reason=("Code can be proved correct by running it, so this goes through the "
                    "generate-test-repair loop rather than a model's first guess."),
            matched=code.group(0))

    files = _FILE_WORK.search(text)
    if files:
        return RouteDecision(
            strategy=Strategy.AGENT,
            # Deliberately the tool-calling leader, not the coding leader: coder-tuned
            # models cannot call tools at all, so the strongest coder is the worst possible
            # choice for a seat whose whole job is driving the filesystem.
            model=local_models.best_model_for("tool_calling", "qwen2.5:1.5b"),
            reason="Needs the filesystem, so it runs as an agent with file tools.",
            matched=files.group(0))

    return RouteDecision(
        strategy=Strategy.COMPLETION,
        model=local_models.best_model_for("instruction_following", "llama3.2:3b"),
        reason="Plain text work with no files and nothing to execute; one completion is enough.",
        matched="")


async def run_task(
    task: str,
    *,
    workspace: str | Path,
    path: str = "solution.py",
    max_repairs: int = 4,
    allow_shell: bool = False,
) -> RoutedResult:
    """Route ``task`` and carry it out, returning a finished result or an honest handoff."""
    import time  # noqa: PLC0415

    started = time.time()
    decision = route(task)
    out = RoutedResult(task=task, decision=decision)

    if decision.strategy is Strategy.ESCALATE:
        out.needs_escalation = True
        out.escalation_packet = (
            f"Not attempted locally.\n\nTASK:\n{task}\n\nWHY:\n{decision.reason}"
        )
        out.seconds = round(time.time() - started, 1)
        return out

    if decision.strategy is Strategy.PIPELINE:
        result = await run_pipeline(task, workspace=workspace, path=path,
                                    coder_model=decision.model or DEFAULT_CODER_MODEL,
                                    max_repairs=max_repairs)
        out.pipeline = result
        out.completed = result.passed
        out.output = result.code
        out.needs_escalation = result.needs_escalation
        out.escalation_packet = result.escalation_packet
        out.seconds = round(time.time() - started, 1)
        return out

    if decision.strategy is Strategy.AGENT:
        run = await run_agent(
            model=decision.model, task=task, workspace=Path(workspace),
            mode=PermissionMode.AUTO if allow_shell else PermissionMode.ACCEPT_EDITS,
            allow_web=False)
        out.completed = run.completed
        out.output = run.answer
        if not run.completed:
            out.needs_escalation = True
            out.escalation_packet = (
                f"A local agent could not finish this.\n\nTASK:\n{task}\n\n"
                f"IT STOPPED BECAUSE: {run.stop_reason}\n\nLAST ANSWER:\n{run.answer[:800]}")
        out.seconds = round(time.time() - started, 1)
        return out

    from .local_agent import generate_code  # noqa: PLC0415 -- shared Ollama call helper

    import asyncio  # noqa: PLC0415
    text = await asyncio.to_thread(generate_code, task, decision.model)
    out.output = text
    out.completed = not text.startswith("ERROR:")
    out.seconds = round(time.time() - started, 1)
    return out
