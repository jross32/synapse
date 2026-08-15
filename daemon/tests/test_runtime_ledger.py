"""The spend ledger: append-only, and readable even when the last line is half-written."""

from __future__ import annotations

from synapse_daemon.runtime_ledger import Entry, read_entries, record, rollup, today_utc


def _entry(runtime: str, at: str, **kw) -> Entry:
    return Entry(at=at, runtime=runtime, ok=kw.pop("ok", True), **kw)


def test_append_and_read_round_trip(tmp_path):
    path = tmp_path / "nested" / "ledger.jsonl"
    record(_entry("claude", "2026-08-15T01:00:00Z", cost_usd=0.17, total_tokens=27589), path=path)
    record(_entry("gemini", "2026-08-15T02:00:00Z", total_tokens=8636, requests=1), path=path)

    entries = read_entries(path)
    assert [e.runtime for e in entries] == ["claude", "gemini"], "file order is preserved"
    assert entries[0].cost_usd == 0.17
    assert entries[1].requests == 1


def test_a_truncated_last_line_does_not_break_the_ledger(tmp_path):
    """A crash mid-append must cost one entry, not the whole history."""
    path = tmp_path / "ledger.jsonl"
    record(_entry("claude", "2026-08-15T01:00:00Z", cost_usd=1.0), path=path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"at":"2026-08-15T02:00:00Z","runtime":"gem')  # power cut

    entries = read_entries(path)
    assert len(entries) == 1 and entries[0].runtime == "claude"


def test_missing_file_reads_as_empty(tmp_path):
    assert read_entries(tmp_path / "never-written.jsonl") == []


def test_rollup_groups_and_counts_failures(tmp_path):
    path = tmp_path / "ledger.jsonl"
    record(_entry("claude", "2026-08-15T01:00:00Z", cost_usd=0.10, seconds=5), path=path)
    record(_entry("claude", "2026-08-15T02:00:00Z", cost_usd=0.20, seconds=7, ok=False), path=path)
    record(_entry("gemini", "2026-08-15T03:00:00Z", total_tokens=100, requests=2), path=path)

    by_runtime = rollup(path)
    assert by_runtime["claude"].calls == 2
    assert by_runtime["claude"].failures == 1
    assert round(by_runtime["claude"].cost_usd, 4) == 0.30
    assert by_runtime["claude"].seconds == 12
    assert by_runtime["gemini"].requests == 2


def test_rollup_records_when_a_runtime_last_ran_out(tmp_path):
    """The signal a planner needs: not just that it failed, but that it was empty."""
    path = tmp_path / "ledger.jsonl"
    record(_entry("copilot", "2026-08-15T01:00:00Z"), path=path)
    record(_entry("copilot", "2026-08-15T02:00:00Z", ok=False,
                  exhausted="You have exceeded your monthly quota"), path=path)

    r = rollup(path)["copilot"]
    assert r.last_exhausted_at == "2026-08-15T02:00:00Z"
    assert rollup(path).get("claude") is None


def test_since_filters_by_date_prefix(tmp_path):
    path = tmp_path / "ledger.jsonl"
    record(_entry("claude", "2026-08-14T23:00:00Z", cost_usd=9.0), path=path)
    record(_entry("claude", "2026-08-15T00:30:00Z", cost_usd=1.0), path=path)

    today = rollup(path, since="2026-08-15")
    assert today["claude"].calls == 1, "yesterday's spend must not count against today"
    assert today["claude"].cost_usd == 1.0


def test_today_utc_is_a_usable_since_value(tmp_path):
    stamp = today_utc()
    assert len(stamp) == 10 and stamp[4] == "-" and stamp[7] == "-"
