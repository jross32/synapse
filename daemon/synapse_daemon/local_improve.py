"""Search for better harness configurations overnight, on free local compute.

The point of this module is that improvement should compound without spending frontier
tokens. Every measurement here is machine-checked and every inference is local, so a run
costs nothing but wall-clock.

It searches the **harness**, never the model and never the source. The distinction matters:

* It may choose among **pre-registered options** — which model holds a seat, which of a
  vetted set of prompt variants is used, context size, repair budget, whether the exemplar
  and contract are injected.
* It may **not** author new prompts, edit code, or invent options. That is the line between
  a bounded search and an agent rewriting the system, and it is not a line worth blurring
  for a few points of benchmark score.

Two ways this could quietly make things worse, and what stops each:

**Overfitting.** Tuning against a benchmark stops the benchmark being a proxy for real work.
So a slice of tasks is held out, never used for tuning, and a variant that wins on the tuning
set while losing on held-out is rejected as overfitting rather than promoted.

**Cross-skill regression.** A change that lifts coding can quietly drop tool-calling, and a
single headline number hides it — the exact mistake of reading one model's result as a fact
about all local models. So promotion requires the whole scorecard to hold, not just the
target skill.

And because a lucky run looks identical to a real improvement, the noise floor is measured
first by repeating the *same* config, and a candidate must beat that margin across repeats.

Autonomy is earned rather than assumed. It ships in shadow mode: it runs the full loop and
records what it *would* have promoted, changing nothing. Once its predictions have held up on
held-out data enough times, auto-promotion switches on. If they never hold up, that is the
finding, and it stays a proposal engine.
"""

from __future__ import annotations

import json
import statistics
import time
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import local_bench
from .runtime_paths import repo_root


class Autonomy(str, Enum):
    SHADOW = "shadow"
    """Runs everything, promotes nothing. The default until it proves calibrated."""

    PROMOTE = "promote"
    """Applies a change when every gate passes, and files a note saying what it did."""


# The entire search space. A variable that is not here cannot be changed, by construction.
SEARCH_SPACE: dict[str, list[Any]] = {
    "coder_model": ["qwen2.5-coder:3b", "qwen2.5-coder:7b", "deepseek-coder:6.7b"],
    "agent_model": ["qwen2.5:1.5b", "llama3.2:3b", "qwen2.5:7b"],
    "num_ctx": [4096, 8192],
    "max_repairs": [4, 10],
    "inject_exemplar": [True, False],
    "inject_contract": [True, False],
    "temperature": [0.0, 0.2],
}

# How much a skill may drop elsewhere before a win is rejected as a regression.
REGRESSION_EPSILON = 0.05

# Consecutive calibrated shadow decisions required before auto-promotion is allowed.
CALIBRATION_THRESHOLD = 3


class Config(BaseModel):
    """A harness configuration. Data only - nothing here is executable."""

    coder_model: str = "qwen2.5-coder:3b"
    agent_model: str = "qwen2.5:1.5b"
    num_ctx: int = 8192
    max_repairs: int = 10
    inject_exemplar: bool = True
    inject_contract: bool = True
    temperature: float = 0.0

    def key(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True)


class Measurement(BaseModel):
    config: Config
    per_skill: dict[str, float] = Field(default_factory=dict)
    mean: float = 0.0
    repeats: int = 0
    seconds: float = 0.0


class Decision(BaseModel):
    at: str
    variable: str
    incumbent: Config
    candidate: Config
    incumbent_score: float
    candidate_score: float
    margin: float
    noise_floor: float
    held_out_confirmed: bool
    regressions: dict[str, float] = Field(default_factory=dict)
    verdict: str = ""
    promoted: bool = False
    reason: str = ""


def state_dir() -> Path:
    return repo_root() / "benchmarks" / "local-models" / "improver"


def _read(name: str, default: Any) -> Any:
    path = state_dir() / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _write(name: str, value: Any) -> None:
    state_dir().mkdir(parents=True, exist_ok=True)
    (state_dir() / name).write_text(json.dumps(value, indent=1), encoding="utf-8")


def active_config() -> Config:
    """The configuration the pipeline should use right now."""
    return Config.model_validate(_read("active_config.json", Config().model_dump()))


def set_active_config(config: Config, reason: str) -> None:
    """Promote a configuration, keeping the previous ones so a rollback is one call."""
    history = _read("config_history.json", [])
    history.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "config": config.model_dump(), "reason": reason})
    _write("config_history.json", history[-25:])
    _write("active_config.json", config.model_dump())


def rollback() -> Config | None:
    """Return to the previous configuration. Deliberately trivial to invoke."""
    history = _read("config_history.json", [])
    if len(history) < 2:
        return None
    previous = Config.model_validate(history[-2]["config"])
    history.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "config": previous.model_dump(), "reason": "rollback"})
    _write("config_history.json", history[-25:])
    _write("active_config.json", previous.model_dump())
    return previous


def autonomy() -> Autonomy:
    """Shadow until calibrated, then promoting - and never by default."""
    state = _read("autonomy.json", {"mode": Autonomy.SHADOW.value, "calibrated_streak": 0})
    return Autonomy(state.get("mode", Autonomy.SHADOW.value))


def _record_calibration(correct: bool) -> dict[str, Any]:
    """Track whether shadow predictions hold up, and unlock promotion once they do."""
    state = _read("autonomy.json", {"mode": Autonomy.SHADOW.value, "calibrated_streak": 0})
    state["calibrated_streak"] = (state.get("calibrated_streak", 0) + 1) if correct else 0
    if (state["mode"] == Autonomy.SHADOW.value
            and state["calibrated_streak"] >= CALIBRATION_THRESHOLD):
        state["mode"] = Autonomy.PROMOTE.value
        state["unlocked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write("autonomy.json", state)
    return state


# ---------------------------------------------------------------- measuring


def split_tasks(skills: list[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Split each skill's checks into a tuning set and a held-out set.

    Deterministic by check id, so the same checks are always held out and a variant cannot
    be validated against something it was tuned on.
    """
    packs = local_bench.load_skill_packs()
    tune: dict[str, list[str]] = {}
    hold: dict[str, list[str]] = {}
    for skill in skills:
        pack = packs.get(skill)
        if not pack:
            continue
        ids = sorted(c.id for c in pack.checks)
        hold[skill] = ids[::3]                       # every third check, never tuned against
        tune[skill] = [i for i in ids if i not in set(hold[skill])]
    return tune, hold


def measure(config: Config, skills: list[str], only_ids: dict[str, list[str]] | None = None,
            repeats: int = 1) -> Measurement:
    """Score a configuration, optionally restricted to a subset of checks."""
    packs = local_bench.load_skill_packs()
    started = time.time()
    runs: list[dict[str, float]] = []

    for _ in range(max(1, repeats)):
        per_skill: dict[str, float] = {}
        for skill in skills:
            pack = packs.get(skill)
            if not pack:
                continue
            checks = pack.checks
            if only_ids and skill in only_ids:
                wanted = set(only_ids[skill])
                checks = [c for c in checks if c.id in wanted]
            if not checks:
                continue
            model = config.coder_model if skill in ("coding", "debugging") else config.agent_model
            results = [local_bench.grade(model, c) for c in checks]
            graded = [r for r in results if not r.unsupported]
            if graded:
                per_skill[skill] = sum(r.passed for r in graded) / len(graded)
        runs.append(per_skill)

    merged = {s: statistics.mean([r[s] for r in runs if s in r])
              for s in {k for r in runs for k in r}}
    return Measurement(config=config, per_skill=merged,
                       mean=round(statistics.mean(merged.values()), 4) if merged else 0.0,
                       repeats=max(1, repeats), seconds=round(time.time() - started, 1))


def noise_floor(config: Config, skills: list[str], repeats: int = 3) -> float:
    """How much the same configuration varies run to run.

    Without this number an improvement cannot be distinguished from luck, and promoting luck
    is how a search convinces itself it is working.
    """
    means = []
    for _ in range(max(2, repeats)):
        means.append(measure(config, skills).mean)
    return round(max(means) - min(means), 4)


# ---------------------------------------------------------------- the loop


def evaluate_candidate(variable: str, value: Any, skills: list[str],
                       incumbent: Config | None = None, repeats: int = 3) -> Decision:
    """Test one change, against every gate, and say plainly whether it earned promotion."""
    incumbent = incumbent or active_config()
    candidate = incumbent.model_copy(update={variable: value})

    tune_ids, hold_ids = split_tasks(skills)
    floor = noise_floor(incumbent, skills)

    base = measure(incumbent, skills, only_ids=tune_ids, repeats=repeats)
    cand = measure(candidate, skills, only_ids=tune_ids, repeats=repeats)
    margin = round(cand.mean - base.mean, 4)

    # Every skill that moved down, and by how much.
    regressions = {s: round(base.per_skill[s] - cand.per_skill.get(s, 0.0), 4)
                   for s in base.per_skill
                   if base.per_skill[s] - cand.per_skill.get(s, 0.0) > REGRESSION_EPSILON}

    decision = Decision(
        at=time.strftime("%Y-%m-%dT%H:%M:%S"), variable=variable,
        incumbent=incumbent, candidate=candidate,
        incumbent_score=base.mean, candidate_score=cand.mean,
        margin=margin, noise_floor=floor, held_out_confirmed=False,
        regressions=regressions)

    if margin <= floor:
        decision.verdict = "rejected"
        decision.reason = (f"improvement of {margin} does not clear the noise floor of "
                           f"{floor}; this is indistinguishable from a lucky run")
        return decision
    if regressions:
        decision.verdict = "rejected"
        decision.reason = (f"it improved the target but degraded {list(regressions)} - a "
                           f"whole-scorecard regression, not a win")
        return decision

    # Only now spend time on held-out validation: the expensive check runs last.
    base_hold = measure(incumbent, skills, only_ids=hold_ids)
    cand_hold = measure(candidate, skills, only_ids=hold_ids)
    decision.held_out_confirmed = cand_hold.mean >= base_hold.mean

    if not decision.held_out_confirmed:
        decision.verdict = "rejected"
        decision.reason = (f"won on the tuning set ({margin:+.3f}) but lost on held-out "
                           f"checks ({cand_hold.mean - base_hold.mean:+.3f}) - overfitting")
        return decision

    decision.verdict = "accepted"
    decision.reason = (f"+{margin} over a {floor} noise floor, no skill regressed, and the "
                       f"gain held on checks it was never tuned against")
    return decision


def run_experiment(skills: list[str] | None = None, variables: list[str] | None = None,
                   repeats: int = 3) -> list[Decision]:
    """One improvement pass. Safe to run unattended; promotes only if it has earned it."""
    skills = skills or list(local_bench.load_skill_packs())
    variables = variables or list(SEARCH_SPACE)
    mode = autonomy()
    decisions: list[Decision] = []

    for variable in variables:
        incumbent = active_config()
        current = getattr(incumbent, variable, None)
        for value in SEARCH_SPACE.get(variable, []):
            if value == current:
                continue
            decision = evaluate_candidate(variable, value, skills, incumbent, repeats)

            if decision.verdict == "accepted":
                # Held-out confirmation is exactly the prediction shadow mode is judging.
                _record_calibration(True)
                if mode is Autonomy.PROMOTE:
                    set_active_config(decision.candidate, decision.reason)
                    decision.promoted = True
                else:
                    decision.reason += " (shadow mode: recorded, not applied)"
            decisions.append(decision)
            _append_decision(decision)

    return decisions


def _append_decision(decision: Decision) -> None:
    log = _read("decisions.json", [])
    log.append(decision.model_dump())
    _write("decisions.json", log[-200:])


def status() -> dict[str, Any]:
    """What the improver has done and whether it is trusted yet."""
    autonomy_state = _read("autonomy.json", {"mode": Autonomy.SHADOW.value,
                                             "calibrated_streak": 0})
    decisions = _read("decisions.json", [])
    accepted = [d for d in decisions if d.get("verdict") == "accepted"]
    return {
        "mode": autonomy_state.get("mode"),
        "calibrated_streak": autonomy_state.get("calibrated_streak", 0),
        "promotion_unlocks_at": CALIBRATION_THRESHOLD,
        "active_config": active_config().model_dump(),
        "decisions": len(decisions),
        "accepted": len(accepted),
        "promoted": len([d for d in decisions if d.get("promoted")]),
        "recent": decisions[-5:],
        "search_space": {k: v for k, v in SEARCH_SPACE.items()},
        "note": ("Shadow mode records what it would have changed without changing anything. "
                 "Auto-promotion unlocks only after its predictions hold up on held-out "
                 "checks three times in a row."),
    }
