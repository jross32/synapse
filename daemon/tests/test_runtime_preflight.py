"""Planning a build against what is left, rather than starting it hopefully.

Reactive exhaustion only fires *after* a call has failed, and the rungs that fail first are
the ones that would have been driving the build. Preflight reads the ledger instead.
"""

from __future__ import annotations

from synapse_daemon import coder_runtimes as cr
from synapse_daemon import runtime_ledger


def _spend(path, runtime: str, at: str, **kw) -> None:
    runtime_ledger.record(
        runtime_ledger.Entry(at=at, runtime=runtime, ok=kw.pop("ok", True), **kw), path=path)


def test_preflight_reports_todays_spend_per_rung(tmp_path):
    path = tmp_path / "ledger.jsonl"
    today = runtime_ledger.today_utc()
    _spend(path, "claude", f"{today}T01:00:00Z", cost_usd=0.17, total_tokens=27589)
    _spend(path, "claude", f"{today}T02:00:00Z", cost_usd=0.03, total_tokens=500)
    _spend(path, "gemini", f"{today}T03:00:00Z", total_tokens=8636, requests=1)

    by_runtime = {s.runtime: s for s in cr.preflight(path=path)}
    assert by_runtime["claude"].calls_today == 2
    assert by_runtime["claude"].cost_usd_today == 0.20
    assert by_runtime["claude"].tokens_today == 28089
    assert by_runtime["gemini"].requests_today == 1
    assert by_runtime["codex"].calls_today == 0, "a rung with no spend reads as zero"


def test_yesterdays_spend_does_not_count_against_today(tmp_path):
    path = tmp_path / "ledger.jsonl"
    _spend(path, "claude", "2020-01-01T01:00:00Z", cost_usd=99.0)
    assert {s.runtime: s for s in cr.preflight(path=path)}["claude"].cost_usd_today == 0.0


def test_a_cooling_rung_is_not_usable_and_says_when_it_returns(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "resolve_command", lambda command: f"/fake/{command}")
    cr.clear_exhausted()
    try:
        cr.mark_exhausted(cr.CoderRuntime.COPILOT, seconds=3600)
        status = {s.runtime: s for s in cr.preflight(path=tmp_path / "l.jsonl")}["copilot"]
        assert not status.usable_now
        assert status.cooling_down_seconds > 3000
        assert "retrying in" in status.note
    finally:
        cr.clear_exhausted()


def test_local_is_always_installed_and_says_what_it_costs_in_time(tmp_path):
    """It needs no binary on PATH, and its real price is wall clock, not money."""
    status = {s.runtime: s for s in cr.preflight(path=tmp_path / "l.jsonl")}["local"]
    assert status.installed and status.usable_now
    assert "overnight" in status.note


def test_a_missing_ledger_is_not_an_error(tmp_path):
    """First ever run: every rung reads as zero spent, nothing raises."""
    statuses = cr.preflight(path=tmp_path / "never-written.jsonl")
    assert len(statuses) == len(cr.DEFAULT_LADDER)
    assert all(s.calls_today == 0 for s in statuses)


def test_record_call_writes_what_the_runtime_reported(tmp_path):
    path = tmp_path / "ledger.jsonl"
    result = cr.RuntimeResult(
        runtime="claude", ok=True, seconds=4.9,
        usage={"model": "claude-sonnet-4-6", "input_tokens": 3, "output_tokens": 4,
               "total_tokens": 27589, "cost_usd": 0.166, "credits": 0.0, "requests": 0})
    cr.record_call(result, path=path)

    entry = runtime_ledger.read_entries(path)[0]
    assert entry.runtime == "claude" and entry.model == "claude-sonnet-4-6"
    assert entry.cost_usd == 0.166 and entry.total_tokens == 27589
    assert entry.ok is True


def test_a_failed_call_is_still_recorded(tmp_path):
    """It spent whatever it spent getting to the failure."""
    path = tmp_path / "ledger.jsonl"
    cr.record_call(cr.RuntimeResult(runtime="copilot", ok=False, seconds=7.0,
                                    exhausted="You have exceeded your monthly quota",
                                    usage={"credits": 0.0}), path=path)

    entry = runtime_ledger.read_entries(path)[0]
    assert entry.ok is False
    assert "exceeded your monthly quota" in entry.exhausted
    assert cr.preflight(path=path)[2].last_exhausted_at == entry.at


def test_recording_never_raises_on_a_broken_usage_dict(tmp_path):
    """Accounting must not be able to take a build down."""
    cr.record_call(cr.RuntimeResult(runtime="gemini", usage={"total_tokens": "not a number"}),
                   path=tmp_path / "ledger.jsonl")
