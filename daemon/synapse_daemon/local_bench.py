"""The local-model scorecard, as a module the app can run rather than a script to remember.

`benchmarks/local-models/testbench.py` already measures six skills with machine-verified
checks. Left as a script it goes stale, because nobody remembers to run it after swapping a
model — and a recommendation engine reading month-old numbers is worse than one reading none,
since it is confidently wrong.

So the bench lives here, callable from the API, with two properties that matter:

* **Skill packs are JSON.** New capabilities can be measured without editing Python, which is
  what stops the bench ossifying around whatever seemed important the day it was written.
* **Every run is kept.** A score alone says little; a score next to last week's says whether a
  change helped. `trend()` is the function the improver depends on.

Nothing is graded by another model. Code is executed, JSON is parsed, tool calls are
inspected — so a model cannot talk its way to a passing mark.
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .runtime_paths import repo_root

OLLAMA = "http://127.0.0.1:11434"


def bench_dir() -> Path:
    return repo_root() / "benchmarks" / "local-models"


def history_dir() -> Path:
    return bench_dir() / "history"


def skill_packs_dir() -> Path:
    return bench_dir() / "skills"


class Check(BaseModel):
    """One graded item. ``kind`` decides how it is asked and how it is marked.

    The expectation fields form a small declarative vocabulary, deliberately: a check that
    can only be expressed as a Python lambda cannot live in a JSON skill pack, and the first
    conversion silently dropped 27% of the suite for exactly that reason. Anything genuinely
    inexpressible should be added here rather than quietly lost, because a bench that measures
    less than it claims is worse than one that measures nothing.
    """

    id: str
    prompt: str
    kind: str = "text"          # text | code | tools | json
    asserts: str = ""           # kind=code: python that must exit 0
    expect_regex: str = ""      # answer must match
    expect_final_number: float | None = None

    # Instruction-following constraints, which are about *shape* rather than content.
    expect_max_chars: int | None = None
    expect_line_count: int | None = None
    expect_starts_with: str = ""
    expect_absent_chars: str = ""      # none of these characters may appear
    expect_absent_regex: str = ""

    # Tool calling. Args are matched as substrings so "Paris" satisfies "paris".
    expect_tool: str = ""
    expect_tool_args: dict[str, str] = Field(default_factory=dict)
    expect_no_tool: bool = False
    expect_only_known_tools: bool = False
    """Invented tool names are a distinct failure from picking the wrong one."""

    tools: list[dict[str, Any]] = Field(default_factory=list)
    weight: float = 1.0


class SkillPack(BaseModel):
    """A named capability and the checks that measure it."""

    skill: str
    description: str = ""
    checks: list[Check] = Field(default_factory=list)


class CheckResult(BaseModel):
    id: str
    passed: bool
    seconds: float = 0.0
    tokens_out: int = 0
    unsupported: bool = False
    detail: str = ""


class SkillResult(BaseModel):
    skill: str
    score: float | None = None
    unsupported: bool = False
    seconds: float = 0.0
    tokens_out: int = 0
    results: list[CheckResult] = Field(default_factory=list)


class ModelResult(BaseModel):
    model: str
    skills: dict[str, SkillResult] = Field(default_factory=dict)
    total_score: float | None = None
    total_seconds: float = 0.0
    total_tokens_out: int = 0


class BenchRun(BaseModel):
    started: str
    finished: str = ""
    host: dict[str, Any] = Field(default_factory=dict)
    skills: list[str] = Field(default_factory=list)
    models: list[ModelResult] = Field(default_factory=list)


# ---------------------------------------------------------------- skill packs


def load_skill_packs() -> dict[str, SkillPack]:
    """Skills from JSON on disk, so measuring something new needs no code change."""
    packs: dict[str, SkillPack] = {}
    directory = skill_packs_dir()
    if not directory.is_dir():
        return packs
    for path in sorted(directory.glob("*.json")):
        try:
            pack = SkillPack.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 -- one bad pack must not hide the others
            continue
        packs[pack.skill] = pack
    return packs


# ---------------------------------------------------------------- running


def call_model(model: str, prompt: str, tools: list[dict[str, Any]] | None = None,
               timeout: float = 180.0) -> tuple[str, list[dict[str, Any]], int, float]:
    payload: dict[str, Any] = {
        "model": model, "messages": [{"role": "user", "content": prompt}],
        "stream": False, "options": {"temperature": 0, "num_ctx": 4096},
    }
    if tools:
        payload["tools"] = tools
    started = time.time()
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        # 400 with tools means the model ships without a tools template. That is a real
        # capability gap and is reported as unsupported, not as a low score.
        return f"__HTTP_{exc.code}__", [], 0, round(time.time() - started, 2)
    except Exception as exc:  # noqa: BLE001
        return f"__ERROR__ {type(exc).__name__}", [], 0, round(time.time() - started, 2)

    msg = body.get("message", {}) or {}
    return (msg.get("content", "") or "", msg.get("tool_calls", []) or [],
            body.get("eval_count", 0) or 0, round(time.time() - started, 2))


def final_number(text: str) -> float | None:
    """The last number in a reply.

    A model that reasons aloud states its conclusion last, so this is what GSM8K-style
    scoring uses. Substring matching gets it wrong in both directions - it accepts "32"
    inside "1032", and rejects a correct answer that arrives after a preamble.
    """
    nums = re.findall(r"-?\d+(?:\.\d+)?", (text or "").replace(",", ""))
    if not nums:
        return None
    try:
        return float(nums[-1])
    except ValueError:
        return None


def extract_code(text: str) -> str:
    fences = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text or "", re.S)
    return (max(fences, key=len) if fences else (text or "")).strip()


def run_code_check(code: str, asserts: str) -> tuple[bool, str]:
    workdir = Path(tempfile.mkdtemp())
    (workdir / "s.py").write_text(code, encoding="utf-8")
    (workdir / "t.py").write_text(asserts + "\nprint('OK')\n", encoding="utf-8")
    try:
        proc = subprocess.run([sys.executable, "t.py"], capture_output=True, text=True,
                              timeout=30, cwd=str(workdir))
        return proc.returncode == 0, (proc.stderr or "")[-200:]
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _grade_tools(check: Check, calls: list[dict[str, Any]]) -> tuple[bool, str]:
    names = [c.get("function", {}).get("name") for c in calls]

    if check.expect_no_tool:
        return (not calls), (f"called {names} when it should have answered directly"
                             if calls else "")

    if check.expect_only_known_tools:
        offered = {t["function"]["name"] for t in check.tools}
        invented = [n for n in names if n not in offered]
        return (not invented), (f"invented tools that were never offered: {invented}"
                                if invented else "")

    for call in calls:
        fn = call.get("function", {})
        if fn.get("name") != check.expect_tool:
            continue
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            # Some models return the argument object as a JSON *string*.
            try:
                args = json.loads(args)
            except Exception:  # noqa: BLE001
                return False, f"arguments were an unparseable string: {args[:60]}"
        missing = {k: v for k, v in check.expect_tool_args.items()
                   if str(v).lower() not in str(args.get(k, "")).lower()}
        if missing:
            return False, f"called {check.expect_tool} with {args}, expected {check.expect_tool_args}"
        return True, ""
    return False, f"called {names}, expected {check.expect_tool}"


def _grade_text(check: Check, text: str) -> tuple[bool, str]:
    """Content and shape constraints, all expressible as data."""
    stripped = text.strip()

    if check.expect_final_number is not None:
        got = final_number(text)
        ok = got is not None and abs(got - check.expect_final_number) < 1e-6
        return ok, f"answered {got}, expected {check.expect_final_number}"

    if check.expect_max_chars is not None:
        ok = 0 < len(stripped) <= check.expect_max_chars
        return ok, f"{len(stripped)} chars, limit {check.expect_max_chars}"

    if check.expect_line_count is not None:
        lines = [ln for ln in stripped.splitlines() if ln.strip()]
        return len(lines) == check.expect_line_count, f"{len(lines)} lines"

    if check.expect_starts_with:
        ok = stripped.upper().startswith(check.expect_starts_with.upper())
        return ok, f"started with {stripped[:24]!r}"

    if check.expect_absent_chars:
        found = [c for c in check.expect_absent_chars if c in stripped]
        return (not found), (f"used forbidden characters {found}" if found else "")

    if check.expect_absent_regex:
        hit = re.search(check.expect_absent_regex, text, re.I)
        return (hit is None), (f"matched what it should avoid: {hit.group(0)!r}" if hit else "")

    if check.expect_regex:
        ok = bool(re.search(check.expect_regex, text, re.I | re.S))
        return ok, text[:80]

    return False, "check declares no expectation"


def grade(model: str, check: Check) -> CheckResult:
    text, calls, tokens, secs = call_model(
        model, check.prompt, check.tools if check.kind == "tools" else None)
    unsupported = text.startswith("__HTTP_400")
    passed, detail = False, ""

    if unsupported:
        detail = "model has no tools template"
    elif check.kind == "code":
        passed, detail = run_code_check(extract_code(text), check.asserts)
    elif check.kind == "tools":
        passed, detail = _grade_tools(check, calls)
    else:
        passed, detail = _grade_text(check, text or "")

    return CheckResult(id=check.id, passed=passed, seconds=secs, tokens_out=tokens,
                       unsupported=unsupported, detail=detail)


def run_bench(models: list[str], skills: list[str] | None = None,
              on_event: Any = None) -> BenchRun:
    packs = load_skill_packs()
    chosen = [s for s in (skills or list(packs)) if s in packs]
    run = BenchRun(started=time.strftime("%Y-%m-%dT%H:%M:%S"), skills=chosen, host=host_info())

    for model in models:
        model_result = ModelResult(model=model)
        for skill in chosen:
            skill_result = SkillResult(skill=skill)
            for check in packs[skill].checks:
                res = grade(model, check)
                skill_result.results.append(res)
                skill_result.seconds += res.seconds
                skill_result.tokens_out += res.tokens_out
                if on_event:
                    on_event({"model": model, "skill": skill, "check": check.id,
                              "passed": res.passed, "unsupported": res.unsupported})
            graded = [r for r in skill_result.results if not r.unsupported]
            skill_result.score = (round(sum(r.passed for r in graded) / len(graded), 3)
                                  if graded else None)
            skill_result.unsupported = len(graded) != len(skill_result.results)
            model_result.skills[skill] = skill_result
            model_result.total_seconds += skill_result.seconds
            model_result.total_tokens_out += skill_result.tokens_out

        scored = [s.score for s in model_result.skills.values() if s.score is not None]
        model_result.total_score = round(statistics.mean(scored), 3) if scored else None
        run.models.append(model_result)
        save_run(run)          # persist per model: a long sweep must not lose finished work

    run.finished = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_run(run)
    return run


def save_run(run: BenchRun) -> Path:
    history_dir().mkdir(parents=True, exist_ok=True)
    path = history_dir() / f"{run.started.replace(':', '-')}.json"
    path.write_text(run.model_dump_json(indent=1), encoding="utf-8")
    return path


def load_runs(limit: int = 20) -> list[dict[str, Any]]:
    if not history_dir().is_dir():
        return []
    out = []
    for path in sorted(history_dir().glob("*.json"))[-limit:]:
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return out


def trend(skill: str, model: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """A skill's score over time — the view that shows a regression rather than implying it."""
    points = []
    for run in load_runs(limit):
        for entry in run.get("models", []):
            if model and entry.get("model") != model:
                continue
            detail = (entry.get("skills") or {}).get(skill)
            if detail and detail.get("score") is not None:
                points.append({"at": run.get("started"), "model": entry.get("model"),
                               "score": detail["score"]})
    return points


def latest_scorecard() -> dict[str, Any]:
    runs = load_runs(1)
    if not runs:
        return {"models": [], "note": "no benchmark has been run on this machine yet"}
    run = runs[-1]
    return {
        "measured_at": run.get("started"),
        "host": run.get("host", {}),
        "models": sorted(
            [{"model": m.get("model"), "total": m.get("total_score"),
              "skills": {k: v.get("score") for k, v in (m.get("skills") or {}).items()},
              "tokens_out": m.get("total_tokens_out")}
             for m in run.get("models", [])],
            key=lambda m: -(m["total"] or -1)),
    }


def host_info() -> dict[str, Any]:
    gpu, vram = None, 0.0
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                              "--format=csv,noheader"], capture_output=True, text=True,
                             timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            name, mem = out.stdout.strip().splitlines()[0].split(",")
            gpu, vram = name.strip(), round(int(re.sub(r"\D", "", mem)) / 1024, 1)
    except Exception:  # noqa: BLE001
        pass
    return {"gpu": gpu, "vram_gb": vram}


def installed_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    return [m["name"] for m in data.get("models", []) if "embed" not in m["name"]]
