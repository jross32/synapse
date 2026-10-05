from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

SOURCE_SUFFIXES = {".tsx", ".jsx", ".ts", ".js", ".css", ".scss", ".html"}
IGNORE_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage", ".turbo"}
TOKEN_FILE_HINTS = {"tokens", "theme", "globals.css", "index.css", "tailwind.config", "design-system"}
HEX_RE = re.compile(r"(?<![\w-])#[0-9a-fA-F]{3,8}\b")
RGB_RE = re.compile(r"\b(?:rgb|rgba|hsl|hsla)\([^\n;]+?\)")
CSS_VAR_DEF_RE = re.compile(r"--[A-Za-z0-9_-]+\s*:")
ARBITRARY_TW_RE = re.compile(r"\b(?:bg|text|border|ring|shadow|rounded|p|px|py|m|mx|my|gap|w|h|min-w|max-w|min-h|max-h)-\[[^\]]+\]")
INLINE_STYLE_RE = re.compile(r"\bstyle\s*=\s*\{\{")
RAW_BUTTON_RE = re.compile(r"<button\b", re.I)
RAW_INPUT_RE = re.compile(r"<(?:input|select|textarea)\b", re.I)


def _tokenish(path: Path) -> bool:
    low = path.as_posix().lower()
    return any(hint in low for hint in TOKEN_FILE_HINTS)


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        yield path


def audit_design_system(root: str | Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    base = Path(root).resolve()
    cfg = config or {}
    allow_inline_styles = bool(cfg.get("allow_inline_styles", False))
    raw_control_warn = bool(cfg.get("warn_raw_controls", True))
    findings: list[dict[str, Any]] = []
    counts = Counter()
    scanned_files = 0

    for path in _iter_files(base):
        scanned_files += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        rel = path.relative_to(base).as_posix()
        is_token_file = _tokenish(path)
        for line_no, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue

            # Colors assigned to CSS custom properties are the token definitions themselves,
            # even when a small project keeps them in styles.css rather than a file named tokens/theme.
            is_css_token_definition = path.suffix.lower() in {".css", ".scss"} and bool(CSS_VAR_DEF_RE.search(line))
            if not is_token_file and not is_css_token_definition:
                for match in HEX_RE.finditer(line):
                    counts["raw_color"] += 1
                    findings.append({"severity": "medium", "kind": "raw_color", "file": rel, "line": line_no, "value": match.group(0), "message": "Hard-coded color outside a token definition."})
                for match in RGB_RE.finditer(line):
                    counts["raw_color"] += 1
                    findings.append({"severity": "medium", "kind": "raw_color", "file": rel, "line": line_no, "value": match.group(0)[:100], "message": "Functional color outside a token definition."})

            for match in ARBITRARY_TW_RE.finditer(line):
                counts["arbitrary_tailwind"] += 1
                findings.append({"severity": "low", "kind": "arbitrary_tailwind", "file": rel, "line": line_no, "value": match.group(0), "message": "Arbitrary Tailwind value may indicate design-token drift."})

            if not allow_inline_styles and INLINE_STYLE_RE.search(line):
                counts["inline_style"] += 1
                findings.append({"severity": "low", "kind": "inline_style", "file": rel, "line": line_no, "value": stripped[:180], "message": "Inline style bypasses the shared visual system unless intentionally dynamic."})

            if raw_control_warn and path.suffix.lower() in {".tsx", ".jsx"}:
                if RAW_BUTTON_RE.search(line):
                    counts["raw_button"] += 1
                    findings.append({"severity": "info", "kind": "raw_button", "file": rel, "line": line_no, "value": stripped[:180], "message": "Raw button: verify the project intentionally bypasses its shared Button primitive."})
                if RAW_INPUT_RE.search(line):
                    counts["raw_form_control"] += 1
                    findings.append({"severity": "info", "kind": "raw_form_control", "file": rel, "line": line_no, "value": stripped[:180], "message": "Raw form control: verify shared field styling, labels, focus, and error states."})

    weighted_debt = (
        counts["raw_color"] * 3
        + counts["arbitrary_tailwind"] * 1.5
        + counts["inline_style"] * 1
        + counts["raw_button"] * 0.25
        + counts["raw_form_control"] * 0.25
    )
    adherence_score = max(0.0, round(100.0 - min(100.0, weighted_debt), 1))
    priority = sorted(findings, key=lambda f: ({"medium": 0, "low": 1, "info": 2}.get(f["severity"], 9), f["file"], f["line"]))
    return {
        "root": str(base),
        "scanned_files": scanned_files,
        "counts": dict(counts),
        "adherence_score": adherence_score,
        "findings": priority,
        "summary": {
            "needs_attention": adherence_score < 85,
            "top_kinds": counts.most_common(5),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Heuristic design-system drift audit")
    parser.add_argument("root")
    parser.add_argument("--config", help="Optional JSON config file")
    args = parser.parse_args(argv)
    config: dict[str, Any] | None = None
    if args.config:
        try:
            config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(json.dumps({"error": str(exc)}, indent=2))
            return 2
    result = audit_design_system(args.root, config)
    print(json.dumps(result, indent=2))
    return 1 if result["summary"]["needs_attention"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
