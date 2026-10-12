"""Focused tests for cli_usage_capture — safe parsing, source/unknown fields,
no double-counting, no secrets, no global wrapping."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synapse_daemon.cli_usage_capture import InvocationRecord, capture, ingest_usage
from synapse_daemon.runtime_ledger import read_entries
from synapse_daemon.runtime_usage import KNOWN_RUNTIMES, usage_source, Usage

# ---------------------------------------------------------------------------
# Fixtures — real stdout samples copied from test_runtime_usage.py
# ---------------------------------------------------------------------------

_CLAUDE_STDOUT = json.dumps({
    "type": "result",
    "total_cost_usd": 0.16612700000000002,
    "usage": {
        "input_tokens": 3,
        "cache_creation_input_tokens": 27582,
        "cache_read_input_tokens": 0,
        "output_tokens": 4,
    },
    "modelUsage": {
        "claude-haiku-4-5-20251001": {"inputTokens": 506, "outputTokens": 12, "costUSD": 0.0006},
        "claude-sonnet-4-6": {"inputTokens": 3, "outputTokens": 4, "costUSD": 0.165561},
    },
})

_GEMINI_STDOUT = (
    "Warning: 256-color support not detected.\n"
    + json.dumps({
        "session_id": "abc",
        "stats": {
            "models": {
                "gemini-2.5-flash": {
                    "api": {"totalRequests": 2},
                    "tokens": {"input": 500, "candidates": 10, "total": 510},
                }
            }
        },
    })
)

_CODEX_STDOUT = "codex\nDone.\n\ntokens used\n12,000\n"
_COPILOT_STDOUT = "Changes    +0 -0\nAI Credits 3.5 (12s)\n"


# ---------------------------------------------------------------------------
# usage_source helper
# ---------------------------------------------------------------------------

class TestUsageSource:
    def test_known_runtime_with_fields_is_provider_reported(self):
        u = Usage(runtime="claude", input_tokens=1, reported_fields={"input_tokens"})
        assert usage_source(u) == "provider_reported"

    def test_known_runtime_empty_fields_is_untracked(self):
        u = Usage(runtime="claude")
        assert usage_source(u) == "untracked"

    def test_unknown_runtime_is_always_untracked(self):
        u = Usage(runtime="my-custom-llm", total_tokens=999,
                  reported_fields={"total_tokens"})
        assert usage_source(u) == "untracked"

    def test_all_known_runtimes_are_in_frozenset(self):
        for rt in ("claude", "gemini", "codex", "copilot"):
            assert rt in KNOWN_RUNTIMES


# ---------------------------------------------------------------------------
# capture() — happy paths
# ---------------------------------------------------------------------------

class TestCaptureHappyPath:
    def test_claude_entry_written_to_ledger(self, tmp_path: Path):
        path = tmp_path / "ledger.jsonl"
        entry = capture(
            InvocationRecord(
                runtime="claude",
                stdout=_CLAUDE_STDOUT,
                ok=True,
                seconds=4.9,
                at="2026-10-11T10:00:00Z",
            ),
            ledger_path=path,
        )

        assert entry.runtime == "claude"
        assert entry.cost_usd == pytest.approx(0.16612700000000002)
        assert entry.total_tokens == 3 + 4 + 27582 + 0
        assert entry.usage_source == "provider_reported"
        assert entry.ok is True
        assert entry.seconds == 4.9

        rows = read_entries(path)
        assert len(rows) == 1
        assert rows[0].at == "2026-10-11T10:00:00Z"

    def test_gemini_entry_aggregates_tokens(self, tmp_path: Path):
        entry = capture(
            InvocationRecord(runtime="gemini", stdout=_GEMINI_STDOUT,
                             at="2026-10-11T11:00:00Z"),
            ledger_path=tmp_path / "ledger.jsonl",
        )
        assert entry.input_tokens == 500
        assert entry.total_tokens == 510
        assert entry.requests == 2
        assert entry.usage_source == "provider_reported"

    def test_codex_total_tokens(self, tmp_path: Path):
        entry = capture(
            InvocationRecord(runtime="codex", stdout=_CODEX_STDOUT,
                             at="2026-10-11T12:00:00Z"),
            ledger_path=tmp_path / "ledger.jsonl",
        )
        assert entry.total_tokens == 12_000
        assert entry.usage_source == "provider_reported"

    def test_copilot_credits(self, tmp_path: Path):
        entry = capture(
            InvocationRecord(runtime="copilot", stdout=_COPILOT_STDOUT,
                             at="2026-10-11T13:00:00Z"),
            ledger_path=tmp_path / "ledger.jsonl",
        )
        assert entry.credits == 3.5
        assert entry.usage_source == "provider_reported"

    def test_model_override_wins_over_parser(self, tmp_path: Path):
        entry = capture(
            InvocationRecord(runtime="claude", stdout=_CLAUDE_STDOUT,
                             model="my-fine-tune", at="2026-10-11T10:00:00Z"),
            ledger_path=tmp_path / "ledger.jsonl",
        )
        assert entry.model == "my-fine-tune"

    def test_model_falls_back_to_parsed_model(self, tmp_path: Path):
        entry = capture(
            InvocationRecord(runtime="claude", stdout=_CLAUDE_STDOUT,
                             at="2026-10-11T10:00:00Z"),
            ledger_path=tmp_path / "ledger.jsonl",
        )
        # The parser picks the model with higher costUSD
        assert entry.model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# capture() — unknown / uninstrumented runtimes
# ---------------------------------------------------------------------------

class TestUnknownRuntime:
    def test_unknown_runtime_entry_is_untracked_zeros(self, tmp_path: Path):
        entry = capture(
            InvocationRecord(runtime="my-local-llm", stdout="some output",
                             at="2026-10-11T09:00:00Z"),
            ledger_path=tmp_path / "ledger.jsonl",
        )
        assert entry.usage_source == "untracked"
        assert entry.total_tokens == 0
        assert entry.cost_usd == 0.0

    def test_known_runtime_empty_output_is_untracked(self, tmp_path: Path):
        entry = capture(
            InvocationRecord(runtime="claude", stdout="",
                             at="2026-10-11T09:00:00Z"),
            ledger_path=tmp_path / "ledger.jsonl",
        )
        assert entry.usage_source == "untracked"
        assert entry.total_tokens == 0


# ---------------------------------------------------------------------------
# capture() — failure recording
# ---------------------------------------------------------------------------

class TestFailureRecording:
    def test_failed_invocation_sets_ok_false(self, tmp_path: Path):
        path = tmp_path / "ledger.jsonl"
        entry = capture(
            InvocationRecord(runtime="claude", stdout="", ok=False,
                             at="2026-10-11T10:00:00Z"),
            ledger_path=path,
        )
        assert entry.ok is False
        rows = read_entries(path)
        assert rows[0].ok is False


# ---------------------------------------------------------------------------
# capture() — timestamp auto-fill
# ---------------------------------------------------------------------------

class TestTimestamp:
    def test_at_is_filled_when_empty(self, tmp_path: Path):
        entry = capture(
            InvocationRecord(runtime="codex", stdout=_CODEX_STDOUT),
            ledger_path=tmp_path / "ledger.jsonl",
        )
        # Should look like 2026-10-11T...Z
        assert len(entry.at) == 20
        assert entry.at.endswith("Z")
        assert "T" in entry.at

    def test_explicit_at_is_preserved(self, tmp_path: Path):
        entry = capture(
            InvocationRecord(runtime="codex", stdout=_CODEX_STDOUT,
                             at="2025-01-01T00:00:00Z"),
            ledger_path=tmp_path / "ledger.jsonl",
        )
        assert entry.at == "2025-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# capture() — no double-counting across multiple calls
# ---------------------------------------------------------------------------

class TestNoDoubleCount:
    def test_two_separate_invocations_produce_two_rows(self, tmp_path: Path):
        path = tmp_path / "ledger.jsonl"
        capture(InvocationRecord(runtime="claude", stdout=_CLAUDE_STDOUT,
                                 at="2026-10-11T10:00:00Z"), ledger_path=path)
        capture(InvocationRecord(runtime="claude", stdout=_CLAUDE_STDOUT,
                                 at="2026-10-11T10:01:00Z"), ledger_path=path)

        rows = read_entries(path)
        assert len(rows) == 2, "each invocation must be its own row"

    def test_mixed_runtimes_written_in_order(self, tmp_path: Path):
        path = tmp_path / "ledger.jsonl"
        capture(InvocationRecord(runtime="claude", stdout=_CLAUDE_STDOUT,
                                 at="2026-10-11T10:00:00Z"), ledger_path=path)
        capture(InvocationRecord(runtime="gemini", stdout=_GEMINI_STDOUT,
                                 at="2026-10-11T10:01:00Z"), ledger_path=path)
        capture(InvocationRecord(runtime="my-local-llm", stdout="",
                                 at="2026-10-11T10:02:00Z"), ledger_path=path)

        rows = read_entries(path)
        assert [r.runtime for r in rows] == ["claude", "gemini", "my-local-llm"]
        # untracked row must not inflate totals
        total_cost = sum(r.cost_usd for r in rows if r.usage_source == "provider_reported")
        assert total_cost == pytest.approx(0.16612700000000002)


# ---------------------------------------------------------------------------
# capture() — bad inputs
# ---------------------------------------------------------------------------

class TestBadInputs:
    def test_non_invocation_record_raises_type_error(self, tmp_path: Path):
        with pytest.raises(TypeError, match="InvocationRecord"):
            capture("not a record", ledger_path=tmp_path / "l.jsonl")  # type: ignore[arg-type]

    def test_non_path_ledger_raises_type_error(self):
        with pytest.raises(TypeError, match="pathlib.Path"):
            capture(InvocationRecord(runtime="claude", stdout=""),
                    ledger_path="/tmp/ledger.jsonl")  # type: ignore[arg-type]

    def test_garbage_stdout_never_raises(self, tmp_path: Path):
        for bad in ("", "{", "not json", '{"usage": "wrong"}', "\x1b[0m\x00"):
            entry = capture(
                InvocationRecord(runtime="claude", stdout=bad,
                                 at="2026-10-11T10:00:00Z"),
                ledger_path=tmp_path / "ledger.jsonl",
            )
            assert entry.total_tokens >= 0


# ---------------------------------------------------------------------------
# ingest_usage() — functional wrapper
# ---------------------------------------------------------------------------

class TestIngestUsage:
    def test_ingest_usage_writes_same_entry_as_capture(self, tmp_path: Path):
        path_a = tmp_path / "a.jsonl"
        path_b = tmp_path / "b.jsonl"

        e_a = capture(
            InvocationRecord(runtime="codex", stdout=_CODEX_STDOUT,
                             ok=True, seconds=2.1, at="2026-10-11T10:00:00Z"),
            ledger_path=path_a,
        )
        e_b = ingest_usage(
            "codex", _CODEX_STDOUT,
            ledger_path=path_b,
            ok=True, seconds=2.1, at="2026-10-11T10:00:00Z",
        )

        assert e_a.total_tokens == e_b.total_tokens
        assert e_a.usage_source == e_b.usage_source
        assert e_a.ok == e_b.ok

    def test_ingest_usage_untracked_runtime(self, tmp_path: Path):
        entry = ingest_usage("local-llama", "some output",
                             ledger_path=tmp_path / "ledger.jsonl",
                             at="2026-10-11T10:00:00Z")
        assert entry.usage_source == "untracked"
        assert entry.total_tokens == 0
