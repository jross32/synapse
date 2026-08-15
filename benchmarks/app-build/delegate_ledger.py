"""Have Gemini write the spend ledger: append-only record + per-runtime rollup."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon import coder_runtimes as cr  # noqa: E402

WS = Path(__file__).resolve().parent / "delegated"
WS.mkdir(parents=True, exist_ok=True)

SPEC = '''Write a module `runtime_ledger.py` using only the standard library.

It records what each AI coding runtime has spent, so a build can be planned before it starts
instead of discovering mid-run that a paid tier is empty.

Expose exactly:

    @dataclass
    class Entry:
        at: str = ""          # ISO-8601 UTC, e.g. "2026-08-15T04:20:00Z"
        runtime: str = ""
        model: str = ""
        ok: bool = False
        seconds: float = 0.0
        input_tokens: int = 0
        output_tokens: int = 0
        total_tokens: int = 0
        cost_usd: float = 0.0
        credits: float = 0.0
        requests: int = 0
        exhausted: str = ""   # non-empty if the runtime reported being out of room

    @dataclass
    class Rollup:
        runtime: str = ""
        calls: int = 0
        failures: int = 0
        seconds: float = 0.0
        total_tokens: int = 0
        cost_usd: float = 0.0
        credits: float = 0.0
        requests: int = 0
        last_exhausted_at: str = ""   # "" if never

    def record(entry: Entry, *, path: Path) -> None
    def read_entries(path: Path, *, since: str = "") -> list[Entry]
    def rollup(path: Path, *, since: str = "") -> dict[str, Rollup]
    def today_utc() -> str

Behaviour:

- `record` appends ONE json object per line (JSONL) to `path`, creating parent directories
  if needed. Appending must never lose an existing line and must never raise on a
  concurrent append - open in append mode and write a single line ending in "\\n".
- `read_entries` returns entries in file order. A malformed or truncated line is SKIPPED,
  not raised - a half-written last line must not make the whole ledger unreadable. A
  missing file returns [].
- `since` is an ISO-8601 prefix filter: an entry is included when `entry.at >= since`
  compares true as plain strings. `since=""` means everything.
- `rollup` groups by runtime. `calls` counts all entries, `failures` counts entries with
  ok=False. `last_exhausted_at` is the newest `at` among entries with a non-empty
  `exhausted`, or "" if none.
- `today_utc` returns today's UTC date as "YYYY-MM-DD", suitable to pass as `since`.

Use `datetime.now(timezone.utc)` (never the deprecated `utcnow`). Do not import anything
outside the standard library.
'''


def main() -> None:
    runtime = cr.CoderRuntime.GEMINI
    print(f"delegating runtime_ledger.py to {runtime.value} ...", flush=True)
    result = cr.write_module(runtime, SPEC, workspace=WS, path="runtime_ledger.py",
                             timeout=900.0)
    print(f"ok={result.ok} seconds={result.seconds:.0f} error={result.error[:200]}")
    print(f"usage: {result.usage}")
    written = WS / "runtime_ledger.py"
    print(f"written: {written.exists()} "
          f"({written.stat().st_size if written.exists() else 0} bytes)")


main()
