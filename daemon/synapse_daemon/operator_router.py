"""Deterministic capability routing for Synapse operator tasks.

This layer does not execute arbitrary actions itself. It turns a natural-language
operator intent plus currently available capabilities into a small, auditable
execution plan. The caller can then dispatch each step through the existing
Synapse/MCP adapters and Flight Recorder.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class OperatorStep:
    capability: str
    action: str
    reason: str
    fallback: str | None = None
    verification: str | None = None
    risk: str = "low"


@dataclass(frozen=True)
class OperatorPlan:
    intent: str
    mode: str
    steps: tuple[OperatorStep, ...]
    missing_capabilities: tuple[str, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "mode": self.mode,
            "steps": [asdict(step) for step in self.steps],
            "missing_capabilities": list(self.missing_capabilities),
            "notes": list(self.notes),
        }


_CAPABILITY_ALIASES = {
    "web_scraper": {"web-scraper", "wbscrper", "scraper"},
    "browser": {"playwright", "browser", "browsermcp"},
    "desktop": {"reflex", "windows", "desktop"},
    "github": {"github"},
    "memory": {"memory"},
    "trace": {"trace", "flight-recorder", "flight_recorder"},
    "watchdogs": {"watchdogs", "watchdog"},
    "shell": {"shell", "system", "synapse"},
}


def normalize_capabilities(values: Iterable[str]) -> set[str]:
    raw = {str(value).strip().lower() for value in values if str(value).strip()}
    out: set[str] = set()
    for canonical, aliases in _CAPABILITY_ALIASES.items():
        if raw.intersection(aliases) or canonical in raw:
            out.add(canonical)
    return out


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def classify_intent(intent: str) -> str:
    text = intent.strip().lower()
    if _has_any(text, ("crash", "broken", "error", "timeout", "stuck", "502", "failed", "failure", "diagnose", "fix")):
        return "diagnose"
    if _has_any(text, ("research", "find", "search", "compare", "price", "deal", "coupon", "latest")):
        return "research"
    if _has_any(text, ("website", "browser", "page", "form", "login", "chrome")):
        return "browser_operate"
    if _has_any(text, ("click", "open", "type", "window", "desktop", "screen", "computer", "pc")):
        return "desktop_operate"
    if _has_any(text, ("test", "build", "code", "repo", "git", "commit", "project", "develop", "implement")):
        return "developer"
    if _has_any(text, ("monitor", "watch", "health", "status", "observe")):
        return "observe"
    return "general"


def build_operator_plan(intent: str, capabilities: Iterable[str]) -> OperatorPlan:
    caps = normalize_capabilities(capabilities)
    mode = classify_intent(intent)
    steps: list[OperatorStep] = []
    missing: list[str] = []
    notes = [
        "Prefer semantic/accessibility or structured APIs before raw coordinates.",
        "Record action/outcome receipts; do not store hidden chain-of-thought.",
    ]

    def add(required: str, action: str, reason: str, *, fallback: str | None = None,
            verification: str | None = None, risk: str = "low") -> None:
        if required in caps:
            steps.append(OperatorStep(required, action, reason, fallback, verification, risk))
        elif required not in missing:
            missing.append(required)

    if mode == "diagnose":
        add("trace", "analyze recent correlated failures", "Start with the failure timeline instead of guessing.")
        add("watchdogs", "inspect protection-chain health", "Separate service death, stale heartbeat, and recovery failure.")
        add("shell", "inspect logs, ports, processes, tests, and repo state", "Structured machine evidence narrows root cause.", verification="re-run the failing health/test check")
        add("desktop", "inspect visible application state only if machine evidence is insufficient", "UI state is a fallback signal.", verification="capture post-fix visible proof")
    elif mode == "research":
        add("web_scraper", "collect structured web evidence", "Use the deep scraper for extraction, network/API inspection, and source evidence.")
        add("browser", "operate authenticated or interaction-heavy pages", "Accessibility-first browser control is faster and more robust than pixels.", fallback="desktop")
        if "web_scraper" not in caps and "browser" not in caps:
            missing.extend([name for name in ("web_scraper", "browser") if name not in missing])
    elif mode == "browser_operate":
        add("browser", "operate the page through accessibility semantics", "Use roles/text/DOM semantics before visual coordinates.", fallback="desktop", verification="re-read page state after each material action")
        add("desktop", "use visual/window control when browser semantics cannot reach the target", "Fallback for browser chrome, dialogs, or inaccessible surfaces.", risk="medium")
    elif mode == "desktop_operate":
        add("desktop", "inspect windows and use semantic/system controls before mouse coordinates", "Desktop control should be observable and recoverable.", verification="confirm resulting window/process state", risk="medium")
        add("trace", "record operator receipts", "Preserve what happened for later diagnosis.")
    elif mode == "developer":
        add("shell", "inspect project, git state, tests, logs, and ports", "Machine-local structured evidence should drive code changes.", verification="run focused tests then project gates")
        add("github", "inspect or update remote repo state when needed", "Keep local and remote state aligned.")
        add("browser", "verify user-facing behavior in a real browser", "Functional UI proof catches integration regressions.", fallback="desktop", verification="capture passing browser proof")
        add("trace", "record build/test/restart outcomes", "Make failures and recoveries explainable later.")
    elif mode == "observe":
        add("watchdogs", "summarize current protection-chain health", "Use one health view instead of scattered process checks.")
        add("trace", "summarize recent events and repeated failures", "Correlated history makes intermittent faults visible.")
    else:
        for capability, action, reason in (
            ("trace", "inspect recent context", "Recent receipts may reveal the shortest path."),
            ("shell", "inspect local state if the task touches this machine", "Prefer direct evidence over assumptions."),
            ("web_scraper", "research external facts when needed", "Use structured evidence for web-dependent work."),
        ):
            if capability in caps:
                steps.append(OperatorStep(capability, action, reason))
        if not steps:
            notes.append("No specialized capability matched; answer directly or request the minimum missing tool.")

    # De-duplicate missing values while preserving order.
    missing = list(dict.fromkeys(missing))
    return OperatorPlan(intent=intent, mode=mode, steps=tuple(steps), missing_capabilities=tuple(missing), notes=tuple(notes))
