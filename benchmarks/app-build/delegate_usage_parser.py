"""Have Gemini write the per-runtime usage parser, then verify it against real output.

Chosen as a delegation because it is the shape Phase C showed works: small, contract-shaped,
and checkable against samples that already exist. Gemini because it is free and idle, codex
is busy, and local is 1-in-5 overnight work.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon import coder_runtimes as cr  # noqa: E402

WS = Path(__file__).resolve().parent / "delegated"
WS.mkdir(parents=True, exist_ok=True)

SPEC = '''Write a module `runtime_usage.py` with no third-party imports (stdlib only).

It reports what one CLI coding run consumed. Expose exactly:

    @dataclass
    class Usage:
        runtime: str = ""
        model: str = ""
        input_tokens: int = 0
        output_tokens: int = 0
        total_tokens: int = 0
        cost_usd: float = 0.0
        credits: float = 0.0
        requests: int = 0

    def parse_usage(runtime: str, stdout: str) -> Usage

`parse_usage` never raises and never returns None. On anything unrecognised it returns
Usage(runtime=runtime) with zeros - a build must not crash because a vendor changed its
output.

Per runtime, parsing REAL output:

1. runtime == "claude": stdout is JSON (possibly with text before/after the object; find the
   outermost {...}). Read total_cost_usd -> cost_usd, usage.input_tokens -> input_tokens,
   usage.output_tokens -> output_tokens. total_tokens = input + output +
   usage.cache_creation_input_tokens + usage.cache_read_input_tokens (treat missing as 0).
   modelUsage is an object keyed by model name; set model to the key with the largest
   costUSD. Example shape:
   {"total_cost_usd":0.166,"usage":{"input_tokens":3,"output_tokens":4,
    "cache_creation_input_tokens":27582,"cache_read_input_tokens":0},
    "modelUsage":{"claude-sonnet-4-6":{"costUSD":0.1655},"claude-haiku-4-5":{"costUSD":0.0005}}}

2. runtime == "gemini": stdout is JSON. stats.models is an object keyed by model name; each
   has api.totalRequests and tokens with keys input, candidates, total, cached. Sum across
   models: input_tokens = sum of tokens.input, output_tokens = sum of tokens.candidates,
   total_tokens = sum of tokens.total, requests = sum of api.totalRequests. model = the key
   with the largest tokens.total. Example:
   {"stats":{"models":{"gemini-3.5-flash":{"api":{"totalRequests":1},
    "tokens":{"input":8335,"candidates":1,"total":8636,"cached":0}}}}}

3. runtime == "codex": plain text containing a line like "tokens used" followed by a number
   which may contain commas, e.g. "tokens used\\n20,835" or "tokens used: 20,835".
   Set total_tokens to that number.

4. runtime == "copilot": plain text containing "AI Credits" followed by a number, which may
   be a decimal, e.g. "AI Credits 0 (7s)" or "AI Credits 1.5". Set credits to that number.

Any other runtime (including "local"): zeros.

Be careful: JSON parsing must tolerate leading warning lines, and a number like "1,200.50"
must parse as 1200.50 not 1.
'''


def main() -> None:
    runtime = cr.CoderRuntime.GEMINI
    print(f"delegating runtime_usage.py to {runtime.value} ...", flush=True)
    result = cr.write_module(runtime, SPEC, workspace=WS, path="runtime_usage.py",
                             timeout=900.0)
    print(f"ok={result.ok} seconds={result.seconds:.0f} error={result.error[:200]}")
    written = WS / "runtime_usage.py"
    print(f"written: {written.exists()} "
          f"({written.stat().st_size if written.exists() else 0} bytes)")


main()
