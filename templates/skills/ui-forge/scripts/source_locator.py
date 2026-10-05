from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SOURCE_SUFFIXES = {".tsx", ".jsx", ".ts", ".js", ".html"}
IGNORE_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage", ".turbo"}
TAG_RE = re.compile(r"<([A-Za-z][A-Za-z0-9._:-]*)\b")
ATTR_PATTERNS = {
    "id": re.compile(r"\bid\s*=\s*[{'\"]+([^}'\"]+)"),
    "testid": re.compile(r"\bdata-testid\s*=\s*[{'\"]+([^}'\"]+)"),
    "aria_label": re.compile(r"\baria-label\s*=\s*[{'\"]+([^}'\"]+)"),
    "class": re.compile(r"\bclass(?:Name)?\s*=\s*[{'\"]+([^}'\"]+)"),
}
TEXT_RE = re.compile(r">\s*([^<{][^<{]{1,120}?)\s*<")
SOURCE_TAG_RE = re.compile(r"^(.*):(\d+):(\d+)$")


def _iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        yield path


def build_source_index(root: str | Path) -> list[dict[str, Any]]:
    base = Path(root).resolve()
    out: list[dict[str, Any]] = []
    for path in _iter_source_files(base):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, 1):
            if "<" not in line:
                continue
            tags = TAG_RE.findall(line)
            if not tags:
                continue
            attrs = {name: (match.group(1).strip() if (match := pattern.search(line)) else "") for name, pattern in ATTR_PATTERNS.items()}
            text_match = TEXT_RE.search(line)
            text = text_match.group(1).strip() if text_match else ""
            out.append({
                "file": path.relative_to(base).as_posix(),
                "line": line_no,
                "tags": tags,
                "id": attrs["id"],
                "testid": attrs["testid"],
                "aria_label": attrs["aria_label"],
                "classes": attrs["class"],
                "text": text,
                "snippet": line.strip()[:500],
            })
    return out


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _class_tokens(value: Any) -> set[str]:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return {token for token in re.split(r"\s+", _norm(value)) if token}


def _probe_attr(probe: dict[str, Any], *names: str) -> Any:
    attributes = probe.get("attributes") if isinstance(probe.get("attributes"), dict) else {}
    dataset = probe.get("dataset") if isinstance(probe.get("dataset"), dict) else {}
    for name in names:
        if probe.get(name):
            return probe.get(name)
        if attributes.get(name):
            return attributes.get(name)
        data_key = name[5:].replace("-", "_") if name.startswith("data-") else name
        if dataset.get(data_key):
            return dataset.get(data_key)
        camel = "".join(part.capitalize() if idx else part for idx, part in enumerate(data_key.split("_")))
        if dataset.get(camel):
            return dataset.get(camel)
    return ""


def _direct_source_match(root: Path, probe: dict[str, Any]) -> dict[str, Any] | None:
    raw = _probe_attr(probe, "ui_forge_source", "data-ui-forge-source")
    match = SOURCE_TAG_RE.match(str(raw or "").replace("\\", "/"))
    if not match:
        return None
    relative, line_raw, column_raw = match.groups()
    relative = relative.lstrip("/")
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    if not target.is_file():
        return None
    line = int(line_raw)
    column = int(column_raw)
    try:
        lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        lines = []
    snippet = lines[line - 1].strip()[:500] if 0 < line <= len(lines) else ""
    return {
        "file": target.relative_to(root).as_posix(),
        "line": line,
        "column": column,
        "tags": [_norm(probe.get("tag"))] if probe.get("tag") else [],
        "id": str(probe.get("id") or ""),
        "testid": str(_probe_attr(probe, "testid", "data-testid") or ""),
        "aria_label": str(_probe_attr(probe, "aria_label", "aria-label") or ""),
        "classes": " ".join(probe.get("classes", [])) if isinstance(probe.get("classes"), list) else str(probe.get("classes") or ""),
        "text": str(probe.get("text") or ""),
        "snippet": snippet,
        "match_score": 200.0,
        "match_reasons": ["direct data-ui-forge-source tag"],
        "ui_forge_id": str(_probe_attr(probe, "ui_forge_id", "data-ui-forge-id") or ""),
    }


def locate_source(root: str | Path, probe: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    base = Path(root).resolve()
    direct = _direct_source_match(base, probe)
    if direct is not None:
        return [direct]

    index = build_source_index(base)
    p_tag = _norm(probe.get("tag"))
    p_id = _norm(probe.get("id"))
    p_testid = _norm(_probe_attr(probe, "testid", "data-testid"))
    p_aria = _norm(_probe_attr(probe, "aria_label", "aria-label"))
    p_text = _norm(probe.get("text"))[:120]
    p_classes = _class_tokens(probe.get("classes") or probe.get("class"))

    ranked: list[tuple[float, dict[str, Any], list[str]]] = []
    for item in index:
        score = 0.0
        reasons: list[str] = []
        tags = {_norm(tag.split(".")[-1]) for tag in item["tags"]}
        if p_tag and p_tag in tags:
            score += 8
            reasons.append("tag")
        if p_id and p_id == _norm(item["id"]):
            score += 50
            reasons.append("id")
        if p_testid and p_testid == _norm(item["testid"]):
            score += 55
            reasons.append("data-testid")
        if p_aria and p_aria == _norm(item["aria_label"]):
            score += 35
            reasons.append("aria-label")
        item_text = _norm(item["text"])
        if p_text and item_text:
            if p_text == item_text:
                score += 35
                reasons.append("exact text")
            elif p_text in item_text or item_text in p_text:
                score += 18
                reasons.append("partial text")
        item_classes = _class_tokens(item["classes"])
        shared = p_classes & item_classes
        if shared:
            score += min(24, len(shared) * 4)
            reasons.append(f"{len(shared)} shared classes")
        if score > 0:
            ranked.append((score, item, reasons))

    ranked.sort(key=lambda row: (-row[0], row[1]["file"], row[1]["line"]))
    return [
        {**item, "match_score": round(score, 2), "match_reasons": reasons}
        for score, item, reasons in ranked[: max(1, int(limit))]
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Locate likely JSX/TSX/HTML source for a rendered DOM probe")
    parser.add_argument("root")
    parser.add_argument("probe_json", help="JSON object or path to a JSON file")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    raw = args.probe_json
    path = Path(raw)
    try:
        probe = json.loads(path.read_text(encoding="utf-8")) if path.exists() else json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    result = locate_source(args.root, probe, args.limit)
    print(json.dumps({"matches": result}, indent=2))
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
