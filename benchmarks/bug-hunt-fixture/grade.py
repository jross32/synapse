#!/usr/bin/env python3
"""Mechanically score a bug-hunt run against answer-key.json.

Usage:
    python grade.py --findings run-findings.json --tokens 14200 [--key answer-key.json]

`findings` is a JSON array of objects, each with a `text` field (the finding description) and an
optional `surface`. Output is a JSON report on stdout with per-bug matches and the headline
efficiency numbers (bugs_per_1k_tokens, false_positive_rate, recall). Zero third-party deps.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _norm(text: str) -> str:
    return " ".join(str(text).lower().split())


def grade(key: dict, findings: list[dict], tokens: int) -> dict:
    bugs = key.get("bugs", [])
    claimed: dict[str, int] = {}  # bug_id -> index of the finding that first matched it
    finding_status: list[str] = []  # per-finding: 'true_positive' | 'duplicate' | 'false_positive'

    for fi, finding in enumerate(findings):
        text = _norm(finding.get("text", "")) + " " + _norm(finding.get("surface", ""))
        matched_bug = None
        for bug in bugs:
            terms = [_norm(t) for t in bug.get("match", [])]
            if any(term and term in text for term in terms):
                matched_bug = bug["id"]
                break
        if matched_bug is None:
            finding_status.append("false_positive")
        elif matched_bug in claimed:
            finding_status.append("duplicate")
        else:
            claimed[matched_bug] = fi
            finding_status.append("true_positive")

    true_positives = len(claimed)
    false_positives = finding_status.count("false_positive")
    duplicates = finding_status.count("duplicate")
    missed = [b["id"] for b in bugs if b["id"] not in claimed]

    # Per-category coverage: which bug classes were found vs missed.
    by_category = {}
    for bug in bugs:
        entry = by_category.setdefault(bug.get("category") or "uncategorized", {"found": 0, "total": 0})
        entry["total"] += 1
        if bug["id"] in claimed:
            entry["found"] += 1

    denom_fp = true_positives + false_positives
    tokens = max(int(tokens), 0)
    return {
        "fixture": key.get("fixture"),
        "total_bugs": len(bugs),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "duplicates": duplicates,
        "missed": missed,
        "recall": round(true_positives / len(bugs), 4) if bugs else 0.0,
        "false_positive_rate": round(false_positives / denom_fp, 4) if denom_fp else 0.0,
        "tokens": tokens,
        "bugs_per_1k_tokens": round(true_positives / (tokens / 1000), 4) if tokens else None,
        "by_category": by_category,
        "matched": {bug_id: findings[fi].get("text", "") for bug_id, fi in sorted(claimed.items())},
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Score a bug-hunt run against the fixture answer key.")
    ap.add_argument("--findings", required=True, help="JSON array of {text, surface?} findings")
    ap.add_argument("--tokens", type=int, required=True, help="total tokens the run spent")
    ap.add_argument("--key", default=str(Path(__file__).with_name("answer-key.json")))
    args = ap.parse_args(argv)

    key = json.loads(Path(args.key).read_text(encoding="utf-8"))
    findings = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    if not isinstance(findings, list):
        print("findings file must be a JSON array", file=sys.stderr)
        return 2

    print(json.dumps(grade(key, findings, args.tokens), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
