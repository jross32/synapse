from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCRIPT_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}
IGNORE_DIRS = {"node_modules", ".git", ".synapse", "dist", "build", ".next", "coverage", ".turbo", "__pycache__"}
MUTATION_MARKERS = (
    ".textContent",
    ".innerText",
    ".innerHTML",
    ".className",
    ".setAttribute(",
    ".toggleAttribute(",
    ".style.",
    ".style[",
    ".value",
)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _iter_scripts(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SCRIPT_SUFFIXES:
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        yield path


def _probe_value(probe: dict[str, Any], *names: str) -> str:
    attrs = probe.get("attributes") if isinstance(probe.get("attributes"), dict) else {}
    dataset = probe.get("dataset") if isinstance(probe.get("dataset"), dict) else {}
    for name in names:
        value = probe.get(name)
        if value:
            return str(value)
        value = attrs.get(name)
        if value:
            return str(value)
        key = name.removeprefix("data-").replace("-", "_")
        value = dataset.get(key)
        if value:
            return str(value)
    return ""


def _aliases_for_id(text: str, element_id: str) -> set[str]:
    if not element_id:
        return set()
    escaped = re.escape(element_id)
    calls = [
        rf"document\.getElementById\(\s*['\"]{escaped}['\"]\s*\)",
        rf"document\.querySelector\(\s*['\"]#{escaped}['\"]\s*\)",
        rf"querySelector\(\s*['\"]#{escaped}['\"]\s*\)",
    ]
    aliases: set[str] = set()
    for call in calls:
        # Object-literal property: phaseTitle: document.getElementById("phaseTitle")
        for match in re.finditer(rf"([A-Za-z_$][\w$]*)\s*:\s*{call}", text):
            aliases.add(match.group(1))
        # Variable/assignment: const phaseTitle = ... or phaseTitle = ...
        for match in re.finditer(rf"([A-Za-z_$][\w$]*)\s*=\s*{call}", text):
            aliases.add(match.group(1))
    return aliases


def _selector_evidence(text: str, probe: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    element_id = str(probe.get("id") or "")
    testid = _probe_value(probe, "testid", "data-testid")
    aria = _probe_value(probe, "aria_label", "aria-label")
    if element_id:
        escaped = re.escape(element_id)
        if re.search(rf"getElementById\(\s*['\"]{escaped}['\"]", text):
            evidence.append("getElementById")
        if re.search(rf"querySelector\(\s*['\"]#{escaped}['\"]", text):
            evidence.append("querySelector-id")
    if testid and testid in text:
        evidence.append("data-testid")
    if aria and aria in text:
        evidence.append("aria-label")
    return evidence


def locate_runtime_owner(root: str | Path, probe: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    base = Path(root).resolve()
    p_id = str(probe.get("id") or "")
    p_text = _norm(probe.get("text"))[:240]
    ranked: list[tuple[float, dict[str, Any]]] = []

    for path in _iter_scripts(base):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        selector_evidence = _selector_evidence(text, probe)
        aliases = _aliases_for_id(text, p_id)
        file_has_selector = bool(selector_evidence)
        relative = path.relative_to(base).as_posix()

        for line_no, line in enumerate(lines, 1):
            normalized = _norm(line)
            mutation = next((marker for marker in MUTATION_MARKERS if marker in line), "")
            reasons: list[str] = []
            score = 0.0

            if p_text and p_text in normalized:
                score += 70
                reasons.append("rendered text literal")
            elif p_text and len(p_text) >= 12:
                words = [word for word in re.findall(r"[a-z0-9]+", p_text) if len(word) >= 4]
                shared = sum(1 for word in words if word in normalized)
                if shared >= 2:
                    score += min(35, 8 * shared)
                    reasons.append(f"{shared} rendered-text words")

            if p_id and p_id in line:
                score += 35
                reasons.append("element id literal")
            if mutation:
                score += 25
                reasons.append(f"DOM mutation {mutation}")
            alias_hits = [alias for alias in aliases if re.search(rf"\b{re.escape(alias)}\b", line)]
            if alias_hits:
                score += 45
                reasons.append(f"selector alias {alias_hits[0]}")
            if file_has_selector:
                score += 20
                reasons.append("file links rendered selector")
            if mutation and (alias_hits or (p_text and p_text in normalized)):
                score += 35
                reasons.append("likely runtime writer")

            # A selector declaration is useful evidence but not normally the writer itself.
            # Do not surface unrelated DOM mutations merely because this file contains the target selector.
            directly_relevant = bool(alias_hits or (p_id and p_id in line) or (p_text and p_text in normalized))
            if score >= 45 and directly_relevant:
                ranked.append(
                    (
                        score,
                        {
                            "file": relative,
                            "line": line_no,
                            "snippet": line.strip()[:500],
                            "match_score": round(score, 2),
                            "match_reasons": reasons,
                            "selector_evidence": selector_evidence,
                            "aliases": sorted(aliases),
                            "mutation": mutation or None,
                            "likely_runtime_writer": bool(mutation and (alias_hits or (p_text and p_text in normalized))),
                        },
                    )
                )

    ranked.sort(key=lambda row: (-row[0], row[1]["file"], row[1]["line"]))
    return [item for _, item in ranked[: max(1, int(limit))]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Locate JavaScript/TypeScript runtime writers for a rendered DOM probe")
    parser.add_argument("root")
    parser.add_argument("probe_json", help="JSON object or path to JSON file")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    raw = args.probe_json
    path = Path(raw)
    try:
        probe = json.loads(path.read_text(encoding="utf-8")) if path.exists() else json.loads(raw)
        if not isinstance(probe, dict):
            raise ValueError("probe must be a JSON object")
        result = locate_runtime_owner(args.root, probe, args.limit)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"matches": result}, indent=2))
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
