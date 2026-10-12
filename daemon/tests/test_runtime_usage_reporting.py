"""Durable, honest usage reporting on RungStatus: provenance, last call, provider-only quota."""

from __future__ import annotations

from datetime import datetime, timezone

from synapse_daemon import coder_runtimes as cr
from synapse_daemon import runtime_ledger


def _status(path, name: str = "claude"):
    return {s.runtime: s for s in cr.preflight(path=path)}[name]


def _fake_installed(monkeypatch):
    monkeypatch.setattr(cr, "resolve_command", lambda command: f"/fake/{command}")


def test_no_ledger_means_unknown_not_zero_claim(tmp_path, monkeypatch):
    _fake_installed(monkeypatch)
    s = _status(tmp_path / "none.jsonl", "codex")
    assert s.usage_source == "none" and s.usage_coverage == "none"
    assert s.last_invocation_at is None and s.last_invocation_ok is None
    assert s.quota_remaining is None and s.quota_reset_at is None


def test_recorded_usage_is_labelled_partial_and_last_call_exposed(tmp_path, monkeypatch):
    _fake_installed(monkeypatch)
    path = tmp_path / "l.jsonl"
    today = runtime_ledger.today_utc()
    runtime_ledger.record(runtime_ledger.Entry(
        at=f"{today}T01:00:00Z", runtime="claude", model="m1", ok=True, total_tokens=10,
        usage_source="provider_reported"), path=path)
    runtime_ledger.record(runtime_ledger.Entry(
        at=f"{today}T02:00:00Z", runtime="claude", model="m2", ok=False,
        usage_source="untracked"), path=path)
    s = _status(path)
    assert s.usage_source == "ledger" and s.usage_coverage == "partial"
    assert s.tracked_calls_today == 1 and s.untracked_calls_today == 1
    assert s.last_invocation_at == f"{today}T02:00:00Z"
    assert s.last_invocation_ok is False and s.last_invocation_model == "m2"
    assert s.quota_remaining is None and s.quota_reset_at is None


def test_quota_only_when_provider_supplied(tmp_path, monkeypatch):
    _fake_installed(monkeypatch)
    path = tmp_path / "l.jsonl"
    runtime_ledger.record(runtime_ledger.Entry(
        at="2026-01-01T00:00:00Z", runtime="gemini", ok=True, total_tokens=5,
        quota_remaining=42.0, quota_reset_at="2026-01-02T00:00:00Z"), path=path)
    runtime_ledger.record(runtime_ledger.Entry(
        at="2026-01-01T01:00:00Z", runtime="gemini", ok=True, total_tokens=5), path=path)
    s = _status(path, "gemini")
    assert s.quota_remaining == 42.0
    assert s.quota_reset_at == "2026-01-02T00:00:00Z"
    assert s.quota_as_of == "2026-01-01T00:00:00Z"


def test_record_call_marks_source_and_quota(tmp_path):
    path = tmp_path / "l.jsonl"
    ok_usage = cr.RuntimeResult(runtime="claude", ok=True, usage={
        "total_tokens": 3, "quota_remaining": 7, "quota_reset_at": "2026-02-01T00:00:00Z"})
    bare = cr.RuntimeResult(runtime="claude", ok=True)
    cr.record_call(ok_usage, path=path)
    cr.record_call(bare, path=path)
    first, second = runtime_ledger.read_entries(path)
    assert first.usage_source == "provider_reported" and first.quota_remaining == 7.0
    assert second.usage_source == "untracked" and second.quota_remaining is None


def test_legacy_ledger_rows_still_read(tmp_path):
    path = tmp_path / "l.jsonl"
    path.write_text('{"at": "2026-01-01T00:00:00Z", "runtime": "claude", "ok": true}\n', encoding="utf-8")
    (entry,) = runtime_ledger.read_entries(path)
    assert entry.usage_source == "" and entry.quota_remaining is None


def _expired(monkeypatch, *, refresh: bool):
    _fake_installed(monkeypatch)
    monkeypatch.setattr(cr, "_claude_oauth_expiry", lambda: datetime(2020, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(cr, "_claude_oauth_has_refresh", lambda: refresh)


def test_stale_oauth_with_refresh_credential_stays_usable(tmp_path, monkeypatch):
    _expired(monkeypatch, refresh=True)
    s = _status(tmp_path / "l.jsonl")
    assert s.usable_now and "refresh" in s.note


def test_stale_oauth_but_cli_succeeded_since_stays_usable(tmp_path, monkeypatch):
    _expired(monkeypatch, refresh=False)
    path = tmp_path / "l.jsonl"
    runtime_ledger.record(runtime_ledger.Entry(
        at="2021-01-01T00:00:00Z", runtime="claude", ok=True), path=path)
    assert _status(path).usable_now


def test_stale_oauth_without_refresh_or_success_is_unusable(tmp_path, monkeypatch):
    _expired(monkeypatch, refresh=False)
    s = _status(tmp_path / "l.jsonl")
    assert not s.usable_now and "re-authentication" in s.note
