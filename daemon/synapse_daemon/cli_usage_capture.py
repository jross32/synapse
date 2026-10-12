"""CLI usage capture — record a structured invocation entry into the runtime ledger.

Design constraints
------------------
* Parse-only: we never wrap or monkey-patch global executables.
* No secrets: the caller supplies only stdout text and timing metadata;
  no env vars, API keys, or file paths from the subprocess environment
  are accepted or forwarded.
* No double-counting: callers must pass the stdout from exactly one
  invocation.  The helper does not re-parse or cache anything.
* Honest about unknowns: when the runtime is uninstrumented or the output
  yielded no numeric fields, usage_source is set to "untracked" and the
  numeric fields stay at zero — totals derived from the ledger must filter
  those rows out before summing costs or tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from synapse_daemon.runtime_ledger import Entry, record
from synapse_daemon.runtime_usage import Usage, parse_usage, usage_source


@dataclass
class InvocationRecord:
    """Caller-supplied metadata for one CLI invocation."""

    runtime: str
    """Identifies the CLI tool: "claude", "codex", "copilot", "gemini", or any
    other string.  Unknown values are accepted and recorded as "untracked"."""

    stdout: str
    """Full captured stdout (and/or stderr) from the invocation, as a plain
    string.  ANSI escape codes are stripped by the underlying parsers."""

    ok: bool = True
    """False when the process exited with a non-zero status or the caller
    otherwise considers the invocation a failure."""

    seconds: float = 0.0
    """Wall-clock seconds the invocation took.  Zero if not measured."""

    at: str = ""
    """ISO-8601 UTC timestamp of the invocation start.  When empty the
    helper fills in the current UTC time."""

    model: str = ""
    """Override the inferred model name.  When non-empty this value wins
    over whatever the parser extracted from stdout."""


def capture(record_: InvocationRecord, *, ledger_path: Path) -> Entry:
    """Parse *record_* and append one Entry to the ledger at *ledger_path*.

    Returns the Entry that was written so callers can inspect or log it.
    The file (and its parent directories) are created on first use.

    Raises
    ------
    TypeError  — if *record_* is not an InvocationRecord or *ledger_path*
                 is not a pathlib.Path.
    """
    if not isinstance(record_, InvocationRecord):
        raise TypeError(f"record_ must be InvocationRecord, got {type(record_).__name__}")
    if not isinstance(ledger_path, Path):
        raise TypeError(f"ledger_path must be pathlib.Path, got {type(ledger_path).__name__}")

    usage: Usage = parse_usage(record_.runtime, record_.stdout)

    at = record_.at
    if not at:
        at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    model = record_.model or usage.model

    src = usage_source(usage)

    entry = Entry(
        at=at,
        runtime=record_.runtime,
        model=model,
        ok=record_.ok,
        seconds=record_.seconds,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        cost_usd=usage.cost_usd,
        credits=usage.credits,
        requests=usage.requests,
        usage_source=src,
    )

    record(entry, path=ledger_path)
    return entry


def ingest_usage(
    runtime: str,
    stdout: str,
    *,
    ledger_path: Path,
    ok: bool = True,
    seconds: float = 0.0,
    at: str = "",
    model: str = "",
) -> Entry:
    """Functional wrapper around :func:`capture` for callers that prefer
    keyword arguments over building an :class:`InvocationRecord` themselves.

    Parameters mirror :class:`InvocationRecord` field-for-field.
    """
    return capture(
        InvocationRecord(
            runtime=runtime,
            stdout=stdout,
            ok=ok,
            seconds=seconds,
            at=at,
            model=model,
        ),
        ledger_path=ledger_path,
    )
