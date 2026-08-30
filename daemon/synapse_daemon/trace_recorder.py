"""Synapse Trace / Flight Recorder.

Records privacy-filtered receipts for observable actions and outcomes. The recorder
never stores hidden chain-of-thought. It stores explicit action summaries, safe
metadata, timings, errors, and normalized runtime observations.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .storage import Storage

_SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|cookie|session[_-]?key|credential)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_ASSIGNMENT_SECRET_RE = re.compile(
    r"(?i)\b(token|secret|password|passwd|api[_-]?key|authorization)\s*=\s*([^\s;&|]+)"
)
_MAX_STRING = 1200
_MAX_DETAILS_DEPTH = 6


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clip(value: str, limit: int = _MAX_STRING) -> str:
    text = value if len(value) <= limit else value[: max(0, limit - 3)] + "..."
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _ASSIGNMENT_SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return text


def redact_details(value: Any, *, depth: int = 0) -> Any:
    """Return JSON-safe, recursively redacted metadata."""
    if depth > _MAX_DETAILS_DEPTH:
        return "[TRUNCATED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _clip(value)
    if isinstance(value, Path):
        return _clip(str(value))
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:80]:
            key_text = str(key)
            if _SECRET_KEY_RE.search(key_text):
                out[key_text] = "[REDACTED]"
            else:
                out[key_text] = redact_details(item, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [redact_details(item, depth=depth + 1) for item in list(value)[:100]]
    return _clip(str(value))


def safe_tool_arguments(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Keep useful tool metadata while avoiding large/sensitive payloads."""
    safe = redact_details(args)
    if not isinstance(safe, dict):
        return {"argument_type": type(args).__name__}

    # File writes can contain arbitrary user data/source. Preserve the target and
    # size, not the full content.
    if tool_name == "synapse_write_file" and "content" in args:
        safe["content"] = f"[OMITTED {len(str(args.get('content') or ''))} chars]"

    # Nested MCP calls may contain screenshots/base64 or form payloads.
    if tool_name == "synapse_call_mcp_tool":
        nested = args.get("arguments")
        if isinstance(nested, dict):
            safe_nested = redact_details(nested)
            for key in ("content", "data", "image", "base64", "text"):
                if isinstance(safe_nested, dict) and key in safe_nested and len(str(safe_nested[key])) > 300:
                    safe_nested[key] = f"[OMITTED {len(str(nested.get(key) or ''))} chars]"
            safe["arguments"] = safe_nested

    return safe


def record_event(
    storage: Storage,
    *,
    source: str,
    category: str,
    action: str,
    status: str = "info",
    severity: str | None = None,
    summary: str = "",
    project_id: str | None = None,
    session_id: str | None = None,
    correlation_id: str | None = None,
    duration_ms: float | None = None,
    error_code: str | None = None,
    details: dict[str, Any] | None = None,
    occurred_at: str | None = None,
    dedupe_key: str | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    safe_summary = _clip(summary, 800)
    safe_details = redact_details(details or {})
    if not isinstance(safe_details, dict):
        safe_details = {"value": safe_details}
    final_severity = severity or ("error" if status == "error" else "warning" if status == "warning" else "info")

    with storage.transaction() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO trace_events (
                id, occurred_at, source, category, action, status, severity,
                summary, project_id, session_id, correlation_id, duration_ms,
                error_code, dedupe_key, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                occurred_at or _now_iso(),
                _clip(source, 120),
                _clip(category, 120),
                _clip(action, 180),
                _clip(status, 40),
                _clip(final_severity, 40),
                safe_summary,
                _clip(project_id, 160) if project_id else None,
                _clip(session_id, 160) if session_id else None,
                _clip(correlation_id, 160) if correlation_id else None,
                float(duration_ms) if duration_ms is not None else None,
                _clip(error_code, 160) if error_code else None,
                dedupe_key,
                json.dumps(safe_details, ensure_ascii=False, separators=(",", ":")),
            ),
        )
    return event_id


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    try:
        details = json.loads(row["details_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        details = {}
    return {
        "id": row["id"],
        "occurred_at": row["occurred_at"],
        "source": row["source"],
        "category": row["category"],
        "action": row["action"],
        "status": row["status"],
        "severity": row["severity"],
        "summary": row["summary"],
        "project_id": row["project_id"],
        "session_id": row["session_id"],
        "correlation_id": row["correlation_id"],
        "duration_ms": row["duration_ms"],
        "error_code": row["error_code"],
        "details": details,
    }


def list_events(
    storage: Storage,
    *,
    limit: int = 100,
    category: str | None = None,
    project_id: str | None = None,
    source: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    for column, value in (
        ("category", category),
        ("project_id", project_id),
        ("source", source),
        ("status", status),
    ):
        if value:
            clauses.append(f"{column} = ?")
            values.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(max(1, min(int(limit), 500)))
    cursor = storage.conn.execute(
        f"""
        SELECT id, occurred_at, source, category, action, status, severity,
               summary, project_id, session_id, correlation_id, duration_ms,
               error_code, details_json
        FROM trace_events
        {where}
        ORDER BY occurred_at DESC
        LIMIT ?
        """,
        values,
    )
    return [_row_to_event(row) for row in cursor.fetchall()]


def _dedupe_key(source: str, raw: str) -> str:
    return hashlib.sha256(f"{source}\0{raw}".encode("utf-8", errors="replace")).hexdigest()


def _tail_lines(path: Path, limit: int = 1200) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return data[-limit:]


def _plain_log_timestamp(raw: str) -> str:
    """Interpret watchdog HH:MM:SS prefixes without pretending old lines are new."""
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2})\b", raw)
    if not match:
        return _now_iso()
    now = datetime.now().astimezone()
    try:
        candidate = now.replace(
            hour=int(match.group(1)),
            minute=int(match.group(2)),
            second=int(match.group(3)),
            microsecond=0,
        )
    except ValueError:
        return _now_iso()
    # A log clock later than "now" almost certainly belongs to yesterday after
    # midnight rollover. This makes the recent-history analyzer useful instead
    # of stamping every imported historical line with ingestion time.
    if candidate > now + timedelta(minutes=5):
        candidate -= timedelta(days=1)
    return candidate.isoformat()


def _classify_plain_watchdog(raw: str) -> tuple[str, str, str]:
    lowered = raw.lower()

    if any(token in lowered for token in ("reachable again", "healthy again", "recovered")):
        return "recovery", "info", "recovered"
    if any(token in lowered for token in ("restarting", "relaunched", "restart requested")):
        return "recovery", "info", "restart"

    if "no daemon listening" in lowered or "process for tunnel" in lowered and "not found" in lowered:
        return "warning", "warning", "dependency_missing"

    failure = any(token in lowered for token in ("failed", "error", "unexpected"))
    if failure:
        terminal_failure = any(
            token in lowered
            for token in ("(3/3)", "taskkill", "could not be terminated", "fatal", "crash")
        )
        if terminal_failure:
            return "error", "error", "failure"
        return "warning", "warning", "check_failed"

    return "info", "info", "log"


def _normalize_json_observation(source: str, payload: dict[str, Any]) -> dict[str, Any]:
    event_type = str(
        payload.get("event")
        or payload.get("type")
        or payload.get("kind")
        or payload.get("reason")
        or "observation"
    )
    lowered = event_type.lower()
    message = str(
        payload.get("message")
        or payload.get("detail")
        or payload.get("title")
        or payload.get("reason")
        or event_type
    )
    status = "info"
    severity = "info"
    if any(token in lowered for token in ("error", "crash", "fail", "stale", "spike", "unexpected")):
        status = "error" if any(token in lowered for token in ("error", "crash", "fail")) else "warning"
        severity = status
    elif any(token in lowered for token in ("restart", "recover", "relaunch", "repair")):
        status = "recovery"
        severity = "info"

    occurred_at = (
        payload.get("timestamp")
        or payload.get("time")
        or payload.get("created_at")
        or payload.get("heartbeat")
        or _now_iso()
    )
    project_id = payload.get("project_id")
    session_id = payload.get("session_id")
    return {
        "source": source,
        "category": "runtime",
        "action": event_type,
        "status": status,
        "severity": severity,
        "summary": _clip(message, 800),
        "project_id": str(project_id) if project_id else None,
        "session_id": str(session_id) if session_id else None,
        "occurred_at": str(occurred_at),
        "details": payload,
    }


def ingest_runtime_sources(storage: Storage, *, per_source_limit: int = 1200) -> dict[str, int]:
    """Import recent monitor/watchdog observations idempotently."""
    local_appdata = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    sources: list[tuple[str, Path, bool]] = [
        ("live-monitor", storage.data_dir / "live-monitor" / "events.jsonl", True),
        ("repair-watchdog", storage.data_dir / "system-watchdog" / "watchdog-events.jsonl", True),
        ("ai-supervisor", storage.data_dir / "ai-supervisor" / "supervisor-events.jsonl", True),
        ("stock-hunter-supervisor", local_appdata / "StockHunter" / "runtime-supervisor.jsonl", True),
        ("stock-hunter-campaign", local_appdata / "StockHunter" / "daily-campaign.jsonl", True),
        ("synapse-daemon-watchdog", storage.data_dir / "daemon-watchdog.log", False),
        ("synapse-tunnel-watchdog", storage.data_dir / "tunnel-watchdog.log", False),
    ]
    imported: dict[str, int] = {}
    for source, path, is_json in sources:
        count = 0
        for raw in _tail_lines(path, per_source_limit):
            raw = raw.strip()
            if not raw:
                continue
            key = _dedupe_key(source, raw)
            try:
                exists = storage.conn.execute(
                    "SELECT 1 FROM trace_events WHERE dedupe_key = ? LIMIT 1", (key,)
                ).fetchone()
            except sqlite3.OperationalError:
                continue
            if exists:
                continue

            if is_json:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {"event": "unparsed_log", "message": raw}
                if not isinstance(payload, dict):
                    payload = {"event": "log", "value": payload}
                event = _normalize_json_observation(source, payload)
            else:
                status, severity, action = _classify_plain_watchdog(raw)
                event = {
                    "source": source,
                    "category": "watchdog",
                    "action": action,
                    "status": status,
                    "severity": severity,
                    "summary": raw,
                    "details": {"path": str(path)},
                    "occurred_at": _plain_log_timestamp(raw),
                }

            try:
                record_event(storage, **event, dedupe_key=key)
                count += 1
            except sqlite3.Error:
                continue
        imported[source] = count
    return imported


def analyze_events(storage: Storage, *, window_hours: int = 24) -> dict[str, Any]:
    hours = max(1, min(int(window_hours), 24 * 30))
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    rows = storage.conn.execute(
        """
        SELECT id, occurred_at, source, category, action, status, severity,
               summary, project_id, session_id, correlation_id, duration_ms,
               error_code, details_json
        FROM trace_events
        WHERE occurred_at >= ?
        ORDER BY occurred_at DESC
        LIMIT 5000
        """,
        (since,),
    ).fetchall()
    events = [_row_to_event(row) for row in rows]

    status_counts = Counter(str(event["status"]) for event in events)
    source_counts = Counter(str(event["source"]) for event in events)
    action_counts = Counter(f"{event['category']}:{event['action']}" for event in events)
    error_events = [
        event
        for event in events
        if event["status"] in {"error", "warning"} or event["severity"] in {"error", "warning"}
    ]
    recoveries = [event for event in events if event["status"] == "recovery"]
    slow = sorted(
        [event for event in events if isinstance(event.get("duration_ms"), (int, float)) and event["duration_ms"] >= 2000],
        key=lambda event: float(event["duration_ms"]),
        reverse=True,
    )[:20]

    repeated = Counter(
        (event["source"], event["action"], _clip(event["summary"], 180))
        for event in error_events
    )
    patterns = [
        {"source": source, "action": action, "summary": summary, "count": count}
        for (source, action, summary), count in repeated.most_common(20)
        if count >= 2
    ]

    recommendations: list[dict[str, str]] = []
    if patterns:
        top = patterns[0]
        recommendations.append(
            {
                "kind": "repeated-error",
                "priority": "high" if int(top["count"]) >= 5 else "medium",
                "message": (
                    f"Repeated {top['source']} / {top['action']} failures detected "
                    f"({top['count']} occurrences). Inspect the correlated timeline before retrying."
                ),
            }
        )
    if len(slow) >= 3:
        recommendations.append(
            {
                "kind": "latency",
                "priority": "medium",
                "message": (
                    f"{len(slow)} operations exceeded 2 seconds. Consider batching repeated checks "
                    "or moving blocking work off the control lane."
                ),
            }
        )
    if status_counts.get("recovery", 0) >= 5:
        recommendations.append(
            {
                "kind": "restart-churn",
                "priority": "medium",
                "message": (
                    "Multiple recovery/restart events occurred in this window. Check whether a supervisor "
                    "is repeatedly treating the same underlying fault instead of fixing its cause."
                ),
            }
        )

    return {
        "window_hours": hours,
        "since": since,
        "totals": {
            "events": len(events),
            "errors_warnings": len(error_events),
            "recoveries": len(recoveries),
            "slow_operations": len(slow),
        },
        "status_counts": dict(status_counts),
        "top_sources": [{"source": key, "count": value} for key, value in source_counts.most_common(12)],
        "top_actions": [{"action": key, "count": value} for key, value in action_counts.most_common(20)],
        "repeated_patterns": patterns,
        "slow_operations": slow,
        "recent_incidents": error_events[:30],
        "recent_recoveries": recoveries[:30],
        "recommendations": recommendations,
    }
