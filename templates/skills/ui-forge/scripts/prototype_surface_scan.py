#!/usr/bin/env python3
"""Scan frontend source for prototype signals that should not survive a production-quality UI pass."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".html", ".vue", ".svelte"}
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".vite", "coverage",
    ".venv", "venv", "__pycache__", "release", "target", ".synapse", "test-results", ".tmp"
}
RULES = [
    ("blocking_prompt", re.compile(r"(?<![.$\w])(?:window\.)?prompt\s*\(", re.I), "Browser prompt() is a prototype interaction."),
    ("blocking_alert", re.compile(r"(?<![.$\w])(?:window\.)?alert\s*\(", re.I), "Browser alert() is a prototype interaction."),
    ("coming_soon", re.compile(r"\bcoming\s+soon\b", re.I), "Visible 'coming soon' copy may indicate an unfinished surface."),
    ("soon_badge", re.compile(r"\bSoon\b"), "Visible 'Soon' badge may indicate an unfinished control."),
    ("next_slice", re.compile(r"\bnext\s+(?:ui\s+)?slice\b", re.I), "Copy explicitly says this UI is not implemented yet."),
    ("local_fallback", re.compile(r"\blocal\s+fallback\b", re.I), "Implementation fallback status is exposed in product copy."),
    ("not_connected", re.compile(r"\bnot\s+connected\b", re.I), "Visible disconnected/provider state may be an unfinished primary surface."),
    ("placeholder_copy", re.compile(r"\b(?:placeholder[- ]only|placeholder (?:page|screen|copy|surface|content)|this is a placeholder)\b", re.I), "Explicit placeholder product copy found."),
    ("todo_copy", re.compile(r"\bTODO\b"), "TODO signal found in a product source file."),
]

def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in DEFAULT_EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on", choices=["none", "prompt", "prototype", "any"], default="prototype")
    args = parser.parse_args()
    root = args.project_root.resolve()
    findings = []
    for path in iter_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines, 1):
            for code, pattern, why in RULES:
                if pattern.search(line):
                    findings.append({
                        "code": code,
                        "file": path.relative_to(root).as_posix(),
                        "line": idx,
                        "excerpt": line.strip()[:240],
                        "message": why,
                    })
    summary = {}
    for item in findings:
        summary[item["code"]] = summary.get(item["code"], 0) + 1
    report = {
        "schema": "ui-forge-prototype-scan-v2",
        "root": str(root),
        "finding_count": len(findings),
        "summary": summary,
        "findings": findings,
    }
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if args.fail_on == "none":
        return 0
    if args.fail_on == "prompt":
        return 2 if any(x["code"] in {"blocking_prompt", "blocking_alert"} for x in findings) else 0
    if args.fail_on == "prototype":
        hard = {"blocking_prompt", "blocking_alert", "next_slice", "local_fallback", "placeholder_copy"}
        return 2 if any(x["code"] in hard for x in findings) else 0
    return 2 if findings else 0

if __name__ == "__main__":
    sys.exit(main())
