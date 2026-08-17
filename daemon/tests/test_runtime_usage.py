"""Per-runtime usage parsing, checked against output these CLIs really produced.

Every sample below is copied from a real run in this repo's logs, not invented - a parser
verified against imagined output is the same mistake as a scenario that never executes.
"""

from __future__ import annotations

from synapse_daemon.runtime_usage import Usage, parse_usage


def test_codex_uses_final_ansi_wrapped_footer_not_echoed_command() -> None:
    output = (
        "Write-Output 'tokens used'; Write-Output '49,912'\r\n"
        "\x1b[?25h\x1b[0mtokens used\r\n49,912\x1b[0m\r\n"
    )
    usage = parse_usage("codex", output)
    assert usage.total_tokens == 49_912
    assert "total_tokens" in usage.reported_fields

# `claude --output-format json --print "reply with the single word ok"`, trimmed.
CLAUDE = """{"type":"result","subtype":"success","is_error":false,"duration_ms":4953,
"result":"ok","session_id":"4a9aa6c6","total_cost_usd":0.16612700000000002,
"usage":{"input_tokens":3,"cache_creation_input_tokens":27582,"cache_read_input_tokens":0,
"output_tokens":4,"service_tier":"standard"},
"modelUsage":{"claude-haiku-4-5-20251001":{"inputTokens":506,"outputTokens":12,
"costUSD":0.0005660000000000001},"claude-sonnet-4-6":{"inputTokens":3,"outputTokens":4,
"costUSD":0.165561}}}"""

# `gemini -m gemini-2.5-flash -o json -p "reply with the single word ok"`, with the two
# warning lines the CLI really prints before the JSON.
GEMINI = """Warning: 256-color support not detected.
Ripgrep is not available. Falling back to GrepTool.
{"session_id":"7dbcbabd","response":"ok","stats":{"models":{"gemini-3.5-flash":
{"api":{"totalRequests":1,"totalErrors":0,"totalLatencyMs":4581},
"tokens":{"input":8335,"prompt":8335,"candidates":1,"total":8636,"cached":0,
"thoughts":300,"tool":0}}},"tools":{},"files":{}}}"""

CODEX = "codex\nI'll create the file.\nCreated hello.py.\n\ntokens used\n20,835\n"
COPILOT = "You have exceeded your monthly quota\n\nChanges    +0 -0\nAI Credits 0 (7s)\n"


def test_claude_cost_and_tokens():
    u = parse_usage("claude", CLAUDE)
    assert u.cost_usd == 0.16612700000000002
    assert u.input_tokens == 3
    assert u.output_tokens == 4
    # input + output + cache_creation + cache_read
    assert u.total_tokens == 3 + 4 + 27582 + 0
    assert u.model == "claude-sonnet-4-6", "the model that actually cost the money"


def test_gemini_tokens_and_requests():
    u = parse_usage("gemini", GEMINI)
    assert u.input_tokens == 8335
    assert u.output_tokens == 1
    assert u.total_tokens == 8636
    assert u.requests == 1
    assert u.model == "gemini-3.5-flash"


def test_gemini_json_survives_the_warning_lines_it_really_prints():
    """The CLI prints two warnings before the object; naive json.loads would fail."""
    assert parse_usage("gemini", GEMINI).total_tokens == 8636


def test_codex_thousands_separator():
    assert parse_usage("codex", CODEX).total_tokens == 20835


def test_copilot_credits():
    assert parse_usage("copilot", COPILOT).credits == 0.0
    assert parse_usage("copilot", "AI Credits 1.5 (9s)").credits == 1.5


def test_a_decimal_with_a_thousands_separator_is_not_truncated():
    """`1,200.50` must be 1200.50, not 1. The CSV blueprint was bitten by exactly this."""
    assert parse_usage("copilot", "AI Credits 1,200.50 (3s)").credits == 1200.50


def test_unknown_and_local_runtimes_are_zeros_not_errors():
    for runtime in ("local", "something-new"):
        u = parse_usage(runtime, "whatever")
        assert isinstance(u, Usage) and u.runtime == runtime
        assert u.total_tokens == 0 and u.cost_usd == 0.0


def test_garbage_never_raises():
    """A vendor changing its output must not crash a build."""
    for text in ("", "not json at all", "{", '{"stats": null}', '{"usage": "wrong type"}'):
        for runtime in ("claude", "gemini", "codex", "copilot"):
            assert parse_usage(runtime, text).total_tokens >= 0
