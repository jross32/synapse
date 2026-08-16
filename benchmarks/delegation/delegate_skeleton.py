"""Delegate the scenario-skeleton generator to codex:low."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon import coder_runtimes as cr  # noqa: E402

WS = Path(__file__).resolve().parent / "delegated"
WS.mkdir(parents=True, exist_ok=True)

SPEC = '''Write `scenario_skeleton.py` using only the standard library.

A "scenario" is a Python snippet that checks a generated module from its CALLER's side. It
runs after `from <module> import *`, so it calls functions by bare name. Writing one is
judgement work, but the boilerplate is not. This generates the boilerplate.

Expose exactly:

    def scenario_skeleton(module: str, functions: list[dict]) -> str

`functions` is a list of `{"name": str, "args": list[str], "doc": str}` (doc may be absent).

Return a Python source string with, in this order:

1. A header comment block, exactly:

    # --- acceptance scenario for <module> -----------------------------------------
    # Written from the CALLER's side: what does code using this module need back?
    # Each TODO below FAILS until you replace it. An unfinished scenario must never pass.

2. For each function, in the given order, a block:

    # <name>(<comma-separated args>)   <- "  # <doc>" appended when doc is non-empty
    _got = <name>(<placeholder args>)
    assert False, (
        "TODO: state what a caller needs from <name>(). It returned %r. "
        "Replace this line with a real assertion." % (_got,))

   Placeholder args: for each arg name, use `0` if the name is exactly "id" or ends with
   "_id", `""` otherwise. Join with ", ". A function with no args gets `<name>()`.

3. Separate blocks with a single blank line. End the file with a trailing newline.

Rules:
- Skip any function whose name starts with "_".
- If `functions` is empty, return only the header block (still ending in a newline).
- The output must be valid Python: `compile(result, "<s>", "exec")` must not raise.
- Never raise. A missing "args" or "doc" key is treated as empty.
'''


def main() -> None:
    result = cr.write_module(cr.CoderRuntime.CODEX, SPEC, workspace=WS,
                             path="scenario_skeleton.py", timeout=900.0)
    cr.record_call(result)
    print(f"ok={result.ok} seconds={result.seconds:.0f} "
          f"tokens={result.usage.get('total_tokens')} error={result.error[:150]}")


main()
