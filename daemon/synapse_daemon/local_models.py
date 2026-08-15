"""Local model intelligence: what this machine can run, and what each model is good at.

Two jobs:

1. **Profile the hardware honestly.** VRAM is the binding constraint for local models, and
   Windows' ``Win32_VideoController.AdapterRAM`` is a 32-bit field that silently caps at
   4 GB — a 6 GB card reports as 4 GB. We ask ``nvidia-smi`` first and only fall back to
   WMI, because a wrong VRAM number produces confidently wrong recommendations.

2. **Turn measured benchmark results into role recommendations.** ``benchmarks/local-models``
   scores every installed model on tool-calling, coding, repair, structured output,
   instruction adherence, review reasoning and vision. This module reads those results and
   answers "which model should do this job on this machine", so squads and any connecting
   AI pick from evidence instead of vibes.

Everything degrades gracefully: no GPU, no Ollama, or no benchmark data each yield a
reduced-but-truthful answer rather than an exception.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- hardware


class GpuInfo(BaseModel):
    name: str
    vram_total_mb: int
    vram_free_mb: int | None = None
    driver: str | None = None


class HardwareProfile(BaseModel):
    os: str
    cpu: str
    cpu_cores: int | None = None
    cpu_threads: int | None = None
    ram_gb: float | None = None
    gpus: list[GpuInfo] = Field(default_factory=list)
    vram_gb: float = 0.0
    """Usable VRAM of the best GPU, in GB. 0 means CPU-only inference."""
    notes: list[str] = Field(default_factory=list)


def _nvidia_smi() -> list[GpuInfo]:
    exe = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
    if not Path(exe).exists() and not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total,memory.free,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:  # noqa: BLE001 -- no NVIDIA GPU is a normal state, not an error
        return []
    if out.returncode != 0:
        return []
    gpus: list[GpuInfo] = []
    for line in out.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            gpus.append(GpuInfo(name=parts[0], vram_total_mb=int(float(parts[1])),
                                vram_free_mb=int(float(parts[2])),
                                driver=parts[3] if len(parts) > 3 else None))
        except ValueError:
            continue
    return gpus


def _cpu_ram() -> tuple[str, int | None, int | None, float | None]:
    cpu = platform.processor() or platform.machine()
    cores = threads = None
    ram = None
    try:
        threads = os.cpu_count()
    except Exception:  # noqa: BLE001
        pass
    if platform.system() == "Windows":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "$c=Get-CimInstance Win32_Processor|Select-Object -First 1;"
                 "$s=Get-CimInstance Win32_ComputerSystem;"
                 "\"$($c.Name)|$($c.NumberOfCores)|$($c.NumberOfLogicalProcessors)"
                 "|$([math]::Round($s.TotalPhysicalMemory/1GB,1))\""],
                capture_output=True, text=True, timeout=25,
            )
            parts = out.stdout.strip().split("|")
            if len(parts) == 4:
                cpu = parts[0].strip() or cpu
                cores = int(parts[1]) if parts[1].strip().isdigit() else cores
                threads = int(parts[2]) if parts[2].strip().isdigit() else threads
                ram = float(parts[3])
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            import resource  # noqa: PLC0415

            pages = os.sysconf("SC_PHYS_PAGES")
            page = os.sysconf("SC_PAGE_SIZE")
            ram = round(pages * page / 1e9, 1)
            del resource
        except Exception:  # noqa: BLE001
            pass
    return cpu, cores, threads, ram


def detect_hardware() -> HardwareProfile:
    cpu, cores, threads, ram = _cpu_ram()
    gpus = _nvidia_smi()
    notes: list[str] = []
    vram_gb = 0.0
    if gpus:
        best = max(gpus, key=lambda g: g.vram_total_mb)
        vram_gb = round(best.vram_total_mb / 1024, 1)
    else:
        notes.append(
            "No NVIDIA GPU detected. Models will run on CPU, which is typically 10-30x "
            "slower; prefer models of 3B parameters or fewer."
        )
    if vram_gb and vram_gb < 6:
        notes.append(
            f"{vram_gb} GB of VRAM is tight. A 7B model at Q4 needs roughly 5 GB plus "
            "context, so it may spill into system RAM and slow down sharply."
        )
    return HardwareProfile(os=f"{platform.system()} {platform.release()}", cpu=cpu,
                           cpu_cores=cores, cpu_threads=threads, ram_gb=ram,
                           gpus=gpus, vram_gb=vram_gb, notes=notes)


# ---------------------------------------------------------------- benchmark knowledge

def _repo_root() -> Path:
    # daemon/synapse_daemon/local_models.py -> repo root
    return Path(__file__).resolve().parents[2]


def benchmark_path() -> Path:
    return _repo_root() / "benchmarks" / "local-models" / "results.json"


# Which measured tasks matter for which kind of work. A role is only as good as its
# weakest required capability, so scoring uses the minimum rather than an average -
# an agent that codes brilliantly but cannot emit a tool call is useless as an agent.
ROLE_TASKS: dict[str, dict[str, Any]] = {
    "tool_agent": {
        "label": "Autonomous agent / squad worker",
        "requires": ["tool_call_simple", "tool_call_select", "instruction_adherence"],
        "why": "Must reliably choose and emit well-formed tool calls, then follow "
               "instructions exactly, or the agent loop derails.",
    },
    "coder": {
        "label": "Writing and fixing code",
        "requires": ["code_generate", "code_repair"],
        "why": "Generated code is executed against real assertions, so this is pass/fail, "
               "not a style judgement.",
    },
    "reviewer": {
        "label": "Reviewing diffs and explaining changes",
        "requires": ["diff_reasoning", "instruction_adherence"],
        "why": "Needs to read a change and say what it means without inventing detail.",
    },
    "structured": {
        "label": "Producing JSON for other software to consume",
        "requires": ["json_output", "instruction_adherence"],
        "why": "Anything downstream that parses the output breaks on stray prose.",
    },
    "vision": {
        "label": "Reading screenshots and images",
        "requires": ["vision_color", "vision_count"],
        "why": "Needed for UI verification and screenshot triage.",
    },
}


# CUDA context, cuBLAS workspaces and framework allocations that exist before a single
# weight is loaded. Measured empirically rather than assumed: on this 6 GB card a 4.68 GB
# model plus a 4k cache spills, which only adds up once this overhead is counted.
VRAM_RESERVE_GB = 0.6


def estimate_vram_fit(model_size_gb: float, vram_gb: float, context_tokens: int = 4096,
                      hidden_size: int = 3584, num_layers: int = 28) -> dict[str, Any]:
    """Will this model fit entirely in GPU memory, and how much context can it hold?

    Spilling even slightly into system RAM is the single largest performance cliff on a
    small card -- measured here as ~6 tok/s versus ~25 for a model that fits -- so "does it
    fit" deserves an answer before a multi-gigabyte download, not after.

    The KV cache is the part people forget. It grows linearly with context: two tensors
    (keys and values) per layer, ``hidden_size`` wide, two bytes per element at fp16. At 4k
    context on a 7B that is roughly 1 GB, which is exactly the difference between fitting
    and not on a 6 GB card.
    """
    if model_size_gb <= 0:
        raise ValueError("model_size_gb must be positive")
    if vram_gb <= 0:
        raise ValueError("vram_gb must be positive")
    if context_tokens <= 0:
        raise ValueError("context_tokens must be positive")

    kv_per_token_gb = (2 * num_layers * hidden_size * 2) / 1e9
    kv_cache_gb = kv_per_token_gb * context_tokens
    available = vram_gb - VRAM_RESERVE_GB
    required = model_size_gb + kv_cache_gb

    # Solve for tokens rather than scaling the requested context: the answer to "how much
    # context can I actually have" is independent of what was asked for.
    spare_for_cache = available - model_size_gb
    if spare_for_cache <= 0:
        max_context = 0
    else:
        max_context = int((spare_for_cache / kv_per_token_gb) // 512 * 512)

    return {
        "fits": required <= available,
        "required_gb": round(required, 2),
        "kv_cache_gb": round(kv_cache_gb, 2),
        "headroom_gb": round(available - required, 2),
        "max_context": max_context,
    }


class ModelProfile(BaseModel):
    name: str
    installed: bool = True
    size_gb: float | None = None
    vram_gb: float | None = None
    fully_on_gpu: bool | None = None
    median_tok_per_s: float | None = None
    load_s: float | None = None
    vision_capable: bool = False
    overall_pass_rate: float | None = None
    task_scores: dict[str, float] = Field(default_factory=dict)
    role_scores: dict[str, float] = Field(default_factory=dict)
    best_for: list[str] = Field(default_factory=list)
    avoid_for: list[str] = Field(default_factory=list)


def load_benchmarks() -> dict[str, ModelProfile]:
    """Read measured results, if a benchmark run has been recorded."""
    path = benchmark_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    profiles: dict[str, ModelProfile] = {}
    for name, run in (data.get("runs") or {}).items():
        tasks = run.get("tasks") or {}
        scores = {tid: t.get("pass_rate", 0.0) for tid, t in tasks.items()}
        vram = run.get("vram") or {}

        role_scores: dict[str, float] = {}
        for role, spec in ROLE_TASKS.items():
            needed = [scores[t] for t in spec["requires"] if t in scores]
            if needed:
                role_scores[role] = round(min(needed), 3)

        best = sorted([r for r, s in role_scores.items() if s >= 0.75],
                      key=lambda r: -role_scores[r])
        avoid = sorted([r for r, s in role_scores.items() if s < 0.5],
                       key=lambda r: role_scores[r])

        profiles[name] = ModelProfile(
            name=name,
            size_gb=vram.get("size_gb"),
            vram_gb=vram.get("vram_gb"),
            fully_on_gpu=vram.get("fully_on_gpu"),
            median_tok_per_s=run.get("median_tok_per_s"),
            load_s=run.get("load_s"),
            vision_capable=bool(run.get("vision_capable")),
            overall_pass_rate=run.get("overall_pass_rate"),
            task_scores=scores,
            role_scores=role_scores,
            best_for=best,
            avoid_for=avoid,
        )
    return profiles


class RoleRecommendation(BaseModel):
    role: str
    label: str
    why: str
    model: str | None = None
    score: float | None = None
    reason: str = ""
    alternatives: list[str] = Field(default_factory=list)


def recommend_for_roles(hw: HardwareProfile | None = None,
                        profiles: dict[str, ModelProfile] | None = None
                        ) -> list[RoleRecommendation]:
    """Pick the best measured model for each role on this machine.

    Selection prefers, in order: a model that actually passes the role's tasks, one that
    fits entirely in VRAM (a CPU spill is the largest speed cliff there is), and then
    raw throughput.
    """
    hw = hw or detect_hardware()
    profiles = profiles if profiles is not None else load_benchmarks()
    out: list[RoleRecommendation] = []

    for role, spec in ROLE_TASKS.items():
        candidates = [p for p in profiles.values() if role in p.role_scores]
        rec = RoleRecommendation(role=role, label=spec["label"], why=spec["why"])
        if not candidates:
            rec.reason = ("No benchmark data yet. Run benchmarks/local-models/bench.py "
                          "to measure the models installed on this machine.")
            out.append(rec)
            continue

        def rank(p: ModelProfile) -> tuple:
            return (
                p.role_scores.get(role, 0.0),
                1 if p.fully_on_gpu else 0,
                p.median_tok_per_s or 0.0,
            )

        ranked = sorted(candidates, key=rank, reverse=True)
        top = ranked[0]
        rec.model = top.name
        rec.score = top.role_scores.get(role)
        rec.alternatives = [p.name for p in ranked[1:3] if p.role_scores.get(role, 0) >= 0.5]

        if rec.score is not None and rec.score >= 0.75:
            speed = f", {top.median_tok_per_s} tok/s" if top.median_tok_per_s else ""
            fit = "fits entirely in VRAM" if top.fully_on_gpu else "spills to CPU and will be slow"
            rec.reason = f"Passed {rec.score:.0%} of this role's tasks; {fit}{speed}."
        else:
            rec.reason = (f"Best available is {top.name} at {rec.score:.0%}, which is not "
                          "reliable enough for unattended work. Use a hosted model for this "
                          "role, or keep a human in the loop.")
        out.append(rec)
    return out


# Everything below is measured on this machine, not assumed. It is served verbatim to any
# AI that reads /ai/context so that "use the local models" costs one read instead of a
# discovery session -- the whole point being to save the expensive model's tokens, which is
# defeated if it has to spend them working out how.
PLAYBOOK: dict[str, Any] = {
    "summary": (
        "Local models run through Ollama at http://127.0.0.1:11434 and cost zero API "
        "tokens. They are slow but free and can run unattended. They are the BOTTOM rung of "
        "the coding ladder, not the default: use the best runtime you have credit for, and "
        "fall to these when it runs out or when the work can be left running overnight."
    ),
    "where_local_models_sit": (
        "The ladder is claude -> codex -> copilot -> local, best first and free last. An "
        "earlier version of this playbook had it the other way round - grind locally, "
        "escalate upward - on the theory that it saved tokens. Measured over two days it did "
        "not: the local tier passes a nine-function stateful module about one run in five, "
        "so as an interactive default it costs more supervision than it saves in tokens. "
        "One run in five is perfectly good overnight, where a fresh attempt costs only time "
        "nobody is waiting on, and the honest unit is attempts-to-first-success rather than "
        "a pass rate. Blueprint builds pick their tier automatically; "
        "POST /api/v1/blueprints/{id}/build records which one wrote each piece."
    ),
    "the_one_rule": (
        "Match the model to the seat, and never put a 1-2B model in charge of anything. "
        "Measured on the same three tasks: a 1.5B agent scored 33%, the same loop with "
        "qwen2.5:7b scored 100%, and a code-orchestrated pipeline with no agent at all "
        "scored 100% in half the time. Capability was the binding constraint, not the "
        "scaffolding - but the pipeline still wins on speed, because it never pays for "
        "tool-calling round trips."
    ),
    "correction_worth_reading": (
        "An earlier version of this playbook said 'the scaffolding is the bottleneck, not "
        "the model'. That was wrong, and wrong in an instructive way: it generalised from a "
        "single 1.5B model to all local models without testing a bigger one in the same "
        "seat. Once qwen2.5:7b was measured in the agent seat it scored 100%. Trust the "
        "scorecard over any narrative, including this one."
    ),
    "for_writing_code": {
        "do": "POST /api/v1/local-ai/pipeline with {spec, path, workspace}",
        "why": (
            "Generates the code, writes a test from the same brief, runs it, and repairs "
            "from the real traceback. Measured 100% pass where an agent loop scored 33%."
        ),
        "then": (
            "If the response has needs_escalation=true, read escalation_packet - it is "
            "self-contained (requirement, current code, the test, the real error) and is "
            "designed so you can fix it in one shot without reading anything else."
        ),
        "raise_max_repairs_freely": (
            "Every attempt is local and free. The only reason it is bounded is that a model "
            "which has failed four times with the same error is not one attempt away."
        ),
    },
    "for_delegating_work_instead_of_doing_it_yourself": {
        "read_first": "DELEGATION.md in the repo root - measured, dated, and re-runnable.",
        "default": (
            "codex at effort=low. Measured 2026-08-15: eight builds across three real "
            "blueprint pieces at three effort levels ALL verified with zero repairs, "
            "including a nine-function storage module the local tier never once finished in "
            "441 minutes. Higher effort bought nothing measurable and cost real time (high "
            "averaged 136s against low's 86s)."
        ),
        "what_delegates_well": (
            "One module, a handful of functions, signatures stated up front, and an "
            "acceptance scenario written from the caller's side that the delegate never "
            "sees. Withholding the contract cost 10 repairs against 3. Nine coupled "
            "functions defeated the local tier entirely; three did not."
        ),
        "what_does_not": (
            "Work where the contract is the thing being decided - writing the spec costs "
            "about as much as writing the code, and you cannot check what you did not "
            "specify. Also surgical edits inside a large file."
        ),
        "read_the_result_honestly": (
            "`passed` means the model agrees with itself: most of those tests were written "
            "by the model that wrote the code. `verified` means the blueprint's own scenario "
            "ran and passed. If a scenario fails on something the model seemingly cannot "
            "fix, suspect the scenario first - on this project that has been the cause more "
            "often than the model has."
        ),
        "check_what_is_left_first": (
            "coder_runtimes.preflight() reports each rung's spend today and whether it is "
            "cooling down. Reactive exhaustion only fires after a call has failed, and the "
            "rung that fails first is the one that was driving the build."
        ),
    },
    "for_building_a_whole_app": {
        "do": "GET /api/v1/blueprints, then POST /api/v1/blueprints/{id}/build",
        "why": (
            "A blueprint is a verified recipe, not a template: it carries the pieces to "
            "build, the contracts each must satisfy, the checks that prove they work, and "
            "the score it achieved last time it ran. Building through one is how a local "
            "model produces something with labelled inputs, escaped output and real auth, "
            "rather than something that merely runs."
        ),
        "guarantees_are_enforced": (
            "Each blueprint's `guarantees` list maps to a check that actually runs. They are "
            "not descriptions - if a build cannot satisfy one, the piece escalates."
        ),
        "composing": (
            "Blueprints declare what they `provide` and `require`. "
            "GET /api/v1/blueprints/{id}/compatible finds what fits with one, and "
            "POST /api/v1/blueprints/stack assembles a set and names any unmet requirement "
            "instead of quietly dropping it."
        ),
        "adding_your_own": (
            "POST /api/v1/blueprints registers one - they are data, so the library grows "
            "without code changes."
        ),
    },
    "for_measuring_and_improving": {
        "scorecard": "GET /api/v1/local-ai/bench - per-skill scores measured on this machine",
        "trend": "GET /api/v1/local-ai/bench/history?skill=coding - is it getting better or worse",
        "measure_now": "POST /api/v1/local-ai/bench/run",
        "improve": (
            "POST /api/v1/local-ai/improve/run searches harness configurations on free local "
            "compute. It starts in shadow mode and only earns the right to change anything "
            "after its predictions hold up on checks it was never tuned against."
        ),
        "why_it_matters": (
            "Recommendations are only as good as the measurements behind them. A stale "
            "scorecard is worse than none, because it is confidently wrong."
        ),
    },
    "for_everything_else": {
        "do": "POST /api/v1/local-ai/agent/run with {model, task, mode}",
        "good_for": (
            "Reading and summarising files, renaming, mechanical edits, first-pass triage, "
            "extracting structure from text - work where being wrong is cheap to detect."
        ),
        "modes": "plan (read-only), accept_edits (files, no shell), auto (shell too), bypass",
    },
    "what_does_not_work": [
        "Extra seats. A planner seat scored identically to coder+reviewer and cost ~18s a "
        "task. A reviewer behind a capable agent took 100% to 100% and added 84s. Seats buy "
        "nothing once the primary model can already do the job.",
        "Putting a 1-2B model in charge. qwen2.5:1.5b calls tools perfectly (100%) but "
        "codes at 70% and writes stubs like '# Your code here'. It is a fine pair of hands "
        "and a poor decision-maker.",
        "Letting a weak model verify its own work: 33% and slower than not verifying. It "
        "runs the code, sees the failure, and cannot act on it. Feedback only helps a model "
        "already strong enough to use it.",
        "Giving a coder-tuned model tools: they ship without a tools template and Ollama "
        "returns HTTP 400. Coders write code; general models call tools.",
        "Writing longer system prompts to get better compliance: made a 1.5B model worse "
        "(33% -> 0%), because instructions crowd out a small context.",
    ],
    "build_modes": {
        "what": ("The user sets how far local models are trusted. Read it from "
                 "/api/v1/profile (preferences.build_mode) and obey it - do not decide for "
                 "yourself, and do not silently exceed it."),
        "assist": "You write the code; local models do bulk mechanical work only.",
        "review": ("DEFAULT. Local models write, machine checks run, then YOU review before "
                   "it reaches the user. Review is not optional in this mode - the two "
                   "defects that shipped in the build-off (a stored XSS hole and a dashboard "
                   "rendering 'undefined') both passed every automated check."),
        "auto": ("Local models write and only the machine checks gate the result. Right for "
                 "boilerplate; wrong for anything a user will look at or trust."),
    },
    "when_to_use_your_own_tokens_instead": (
        "Work needing judgement rather than verification - architecture, security review, "
        "anything where correctness cannot be checked by running it. Local models are safe "
        "where a program can prove the answer, and unreliable where it cannot."
    ),
    "endpoints": {
        "what_this_machine_can_run": "GET /api/v1/local-ai/models",
        "hardware": "GET /api/v1/local-ai/hardware",
        "write_code": "POST /api/v1/local-ai/pipeline",
        "build_a_whole_app": "POST /api/v1/blueprints/{id}/build",
        "what_can_be_built": "GET /api/v1/blueprints",
        "model_scorecard": "GET /api/v1/local-ai/bench",
        "run_an_agent": "POST /api/v1/local-ai/agent/run",
        "raw_completion": "POST http://127.0.0.1:11434/api/chat",
    },
    "measured_in": "benchmarks/local-models/REPORT.md and SQUAD_REPORT.md",
}


def skill_scores() -> dict[str, dict[str, float]]:
    """Per-skill scores from the most recent testbench sweep: ``{skill: {model: score}}``.

    Separate from ``load_benchmarks`` because the two measure different things. That one
    records speed and VRAM fit; this one records what each model is actually *good at*,
    which is what routing needs - the fastest model on this machine is also one of the
    weakest coders, so picking by speed picks wrong.

    Returns an empty mapping when no sweep has been run, and callers fall back to their
    defaults rather than pretending to have evidence.
    """
    history = _repo_root() / "benchmarks" / "local-models" / "history"
    if not history.is_dir():
        return {}
    runs = sorted(history.glob("*.json"))
    if not runs:
        return {}
    try:
        data = json.loads(runs[-1].read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- a truncated run must not break routing
        return {}

    out: dict[str, dict[str, float]] = {}
    for entry in data.get("models", []):
        name = entry.get("model")
        for skill, detail in (entry.get("skills") or {}).items():
            score = (detail or {}).get("score")
            if name and score is not None:
                out.setdefault(skill, {})[name] = float(score)
    return out


def best_model_for(skill: str, fallback: str = "") -> str:
    """Highest measured scorer for ``skill``; ``fallback`` when nothing has been measured."""
    scores = skill_scores().get(skill) or {}
    return max(scores, key=scores.__getitem__) if scores else fallback


def summarize_for_ai(hw: HardwareProfile | None = None) -> dict[str, Any]:
    """Compact, honest picture for injection into /ai/context.

    Any AI connecting to Synapse should be able to read this and immediately know which
    local models exist, what each is measured to be good at, and how to call them - so it
    can offload work that doesn't need a frontier model.
    """
    hw = hw or detect_hardware()
    profiles = load_benchmarks()
    recs = recommend_for_roles(hw, profiles)

    models = []
    for p in sorted(profiles.values(), key=lambda x: -(x.overall_pass_rate or 0)):
        models.append({
            "name": p.name,
            "size_gb": p.size_gb,
            "speed_tok_per_s": p.median_tok_per_s,
            "fully_on_gpu": p.fully_on_gpu,
            "vision": p.vision_capable,
            "overall_pass_rate": p.overall_pass_rate,
            "best_for": p.best_for,
            "avoid_for": p.avoid_for,
        })

    return {
        "hardware": {
            "gpu": hw.gpus[0].name if hw.gpus else None,
            "vram_gb": hw.vram_gb,
            "ram_gb": hw.ram_gb,
            "cpu_threads": hw.cpu_threads,
            "notes": hw.notes,
        },
        "models": models,
        "recommended_by_role": [
            {"role": r.role, "model": r.model, "score": r.score, "reason": r.reason}
            for r in recs
        ],
        "playbook": PLAYBOOK,
        "caveat": (
            "Scores come from benchmarks/local-models/bench.py run on this machine and are "
            "measured, not estimated. A role with no passing model means the work should not "
            "be delegated locally without supervision."
        ),
    }
