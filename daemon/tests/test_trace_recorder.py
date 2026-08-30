from __future__ import annotations

import json
from pathlib import Path

from synapse_daemon.storage import Storage
from synapse_daemon.trace_recorder import (
    _classify_plain_watchdog,
    _plain_log_timestamp,
    analyze_events,
    ingest_runtime_sources,
    list_events,
    record_event,
    safe_tool_arguments,
)


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


def test_trace_records_and_redacts_sensitive_metadata(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    event_id = record_event(
        storage,
        source="mcp",
        category="tool",
        action="synapse_run_command",
        status="success",
        summary="command completed",
        project_id="synapse",
        duration_ms=123.4,
        details={
            "token": "super-secret",
            "nested": {"api_key": "abc123", "safe": "visible"},
            "command": "curl -H 'Authorization=secret-value' http://127.0.0.1",
        },
    )

    events = list_events(storage, limit=10)
    assert events[0]["id"] == event_id
    assert events[0]["details"]["token"] == "[REDACTED]"
    assert events[0]["details"]["nested"]["api_key"] == "[REDACTED]"
    assert events[0]["details"]["nested"]["safe"] == "visible"
    assert "secret-value" not in json.dumps(events[0]["details"])
    assert events[0]["duration_ms"] == 123.4


def test_safe_tool_arguments_omits_file_write_body() -> None:
    safe = safe_tool_arguments(
        "synapse_write_file",
        {"path": r"C:\tmp\a.txt", "content": "secret-ish body" * 100},
    )

    assert safe["path"] == r"C:\tmp\a.txt"
    assert str(safe["content"]).startswith("[OMITTED ")
    assert "secret-ish body" not in str(safe["content"])


def test_runtime_ingest_is_idempotent(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    monitor_dir = storage.data_dir / "live-monitor"
    monitor_dir.mkdir(parents=True)
    line = json.dumps(
        {
            "type": "resource_spike",
            "timestamp": "2026-08-29T23:00:00+00:00",
            "message": "CPU high",
        }
    )
    (monitor_dir / "events.jsonl").write_text(line + "\n", encoding="utf-8")

    first = ingest_runtime_sources(storage)
    second = ingest_runtime_sources(storage)

    assert first["live-monitor"] == 1
    assert second["live-monitor"] == 0
    events = list_events(storage, limit=10, source="live-monitor")
    assert len(events) == 1
    assert events[0]["action"] == "resource_spike"
    assert events[0]["status"] == "warning"


def test_analysis_detects_repeated_errors_recoveries_and_slow_work(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    for _ in range(5):
        record_event(
            storage,
            source="mcp",
            category="tool",
            action="synapse_call_mcp_tool",
            status="error",
            summary="reflex timed out",
            duration_ms=2500,
        )
    for _ in range(5):
        record_event(
            storage,
            source="watchdog",
            category="runtime",
            action="restart",
            status="recovery",
            summary="service restarted",
        )

    analysis = analyze_events(storage, window_hours=24)

    assert analysis["totals"]["errors_warnings"] == 5
    assert analysis["totals"]["recoveries"] == 5
    assert analysis["totals"]["slow_operations"] == 5
    kinds = {item["kind"] for item in analysis["recommendations"]}
    assert "repeated-error" in kinds
    assert "latency" in kinds
    assert "restart-churn" in kinds


def test_plain_watchdog_classification_separates_transient_and_terminal_failures() -> None:
    assert _classify_plain_watchdog(
        "00:35:28 [tunnel-watchdog] public URL check failed (1/3) for PID 10532"
    ) == ("warning", "warning", "check_failed")
    assert _classify_plain_watchdog(
        "00:35:28 [tunnel-watchdog] public URL check failed (3/3) for PID 10532"
    ) == ("error", "error", "failure")
    assert _classify_plain_watchdog(
        "00:36:15 [tunnel-watchdog] tunnel reachable again (PID 10532)"
    ) == ("recovery", "info", "recovered")
    assert _classify_plain_watchdog(
        "00:49:18 [tunnel-watchdog] no daemon listening on port 7878 (1/3) -- may just be mid-restart"
    ) == ("warning", "warning", "dependency_missing")


def test_plain_watchdog_timestamp_uses_log_clock_instead_of_ingest_time() -> None:
    stamp = _plain_log_timestamp("00:01:02 [watchdog] example")
    parsed = __import__("datetime").datetime.fromisoformat(stamp)
    assert (parsed.hour, parsed.minute, parsed.second) == (0, 1, 2)
    assert parsed.tzinfo is not None
