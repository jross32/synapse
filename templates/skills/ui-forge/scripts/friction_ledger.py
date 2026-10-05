from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SEVERITIES = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize(text: str) -> str:
    text = re.sub(r"[A-Fa-f0-9]{8,}", "<id>", text.lower())
    text = re.sub(r"\d+", "<n>", text)
    return " ".join(text.split())


def _fingerprint(kind: str, phase: str, summary: str) -> str:
    material = f"{kind.strip().lower()}|{phase.strip().lower()}|{_normalize(summary)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": "ui-forge-friction-ledger-v1", "events": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ledger must be a JSON object")
    if payload.get("schema") != "ui-forge-friction-ledger-v1":
        raise ValueError("unsupported ledger schema")
    if not isinstance(payload.get("events"), dict):
        raise ValueError("events must be an object")
    return payload


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record(
    payload: dict[str, Any],
    *,
    kind: str,
    phase: str,
    summary: str,
    severity: str,
    context: str | None = None,
    proposed_fix: str | None = None,
) -> dict[str, Any]:
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {sorted(SEVERITIES)}")
    fp = _fingerprint(kind, phase, summary)
    now = _now()
    events = payload["events"]
    event = events.get(fp)
    if event is None:
        event = {
            "fingerprint": fp,
            "kind": kind,
            "phase": phase,
            "summary": summary,
            "severity": severity,
            "occurrences": 0,
            "first_seen": now,
            "last_seen": now,
            "contexts": [],
            "proposed_fixes": [],
            "promoted": False,
        }
        events[fp] = event
    event["occurrences"] += 1
    event["last_seen"] = now
    if SEVERITIES[severity] > SEVERITIES.get(event.get("severity", "low"), 1):
        event["severity"] = severity
    if context and context not in event["contexts"]:
        event["contexts"].append(context)
        event["contexts"] = event["contexts"][-8:]
    if proposed_fix and proposed_fix not in event["proposed_fixes"]:
        event["proposed_fixes"].append(proposed_fix)
        event["proposed_fixes"] = event["proposed_fixes"][-8:]
    event["promoted"] = (
        event["occurrences"] >= 2
        or SEVERITIES[event["severity"]] >= SEVERITIES["high"]
    )
    return event


def report(payload: dict[str, Any]) -> dict[str, Any]:
    events = list(payload.get("events", {}).values())
    events.sort(
        key=lambda item: (
            not bool(item.get("promoted")),
            -SEVERITIES.get(str(item.get("severity", "low")), 1),
            -int(item.get("occurrences", 0)),
            str(item.get("last_seen", "")),
        )
    )
    promoted = [item for item in events if item.get("promoted")]
    return {
        "total_patterns": len(events),
        "promoted_patterns": len(promoted),
        "needs_workflow_improvement": bool(promoted),
        "top_patterns": events[:10],
        "promotion_rule": "two occurrences or one high/critical occurrence",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deduplicated self-improvement ledger for UI Forge friction")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("ledger")
    rec.add_argument("--kind", required=True)
    rec.add_argument("--phase", required=True)
    rec.add_argument("--summary", required=True)
    rec.add_argument("--severity", choices=sorted(SEVERITIES), default="medium")
    rec.add_argument("--context")
    rec.add_argument("--proposed-fix")

    rep = sub.add_parser("report")
    rep.add_argument("ledger")

    args = parser.parse_args(argv)
    path = Path(args.ledger)
    try:
        payload = _load(path)
        if args.command == "record":
            event = record(
                payload,
                kind=args.kind,
                phase=args.phase,
                summary=args.summary,
                severity=args.severity,
                context=args.context,
                proposed_fix=args.proposed_fix,
            )
            _save(path, payload)
            output = {"recorded": event, "report": report(payload)}
        else:
            output = report(payload)
        print(json.dumps(output, indent=2, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
