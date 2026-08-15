"""Delegate the pure half of blueprint distillation to codex:low.

Split per DELEGATION.md: the file-scanning analysis has a stated contract and is checkable
against builds that already exist on disk, so it delegates. Turning its output into
Blueprint/Piece objects needs the surrounding types, so that stays hand-written.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon import coder_runtimes as cr  # noqa: E402

WS = Path(__file__).resolve().parent / "delegated"
WS.mkdir(parents=True, exist_ok=True)

SPEC = '''Write `build_scan.py` using only the standard library (ast, pathlib, typing).

It reads a directory containing a working Python app and reports its structure, so a
"blueprint" can later be drafted from it. Pure analysis: it must not import the app, only
parse it with `ast`.

Expose exactly:

    def scan_build(directory) -> list[dict]

`directory` is a str or pathlib.Path. Return one dict per module, sorted by `module` name:

    {
      "module": "storage",            # filename without .py
      "path": "storage.py",
      "doc": "first line of the module docstring, or ''",
      "functions": [                  # public, module-level, in source order
         {"name": "create_user", "args": ["email", "password_hash"], "doc": "first line or ''"}
      ],
      "constants": ["DB"],            # module-level ALL_CAPS assignments
      "imports_local": ["passwords"], # other modules IN THIS DIRECTORY that it imports
      "is_entrypoint": false          # see below
    }

Rules:

- Consider only `*.py` files directly in `directory` (not subdirectories).
- SKIP a file when its name starts with `_` or `test_`, or ends with `_test.py`, or the name
  is `conftest.py` or `setup.py`. These are scaffolding, not the app.
- "public, module-level" means a `def` or `async def` at top level whose name does not start
  with `_`. Nested functions and methods inside classes are NOT included.
- `args` is the positional parameter names in order, excluding `self`.
- `imports_local` lists modules imported with `import X` or `from X import ...` where a file
  named `X.py` exists in the same directory and X is not this module itself. Sorted, no
  duplicates. Relative imports (`from . import X`) count too.
- `is_entrypoint` is True when the module contains `if __name__ == "__main__":` OR defines a
  top-level function named `main`.
- A file that cannot be parsed (SyntaxError) is SKIPPED, not raised - one broken file must
  not make the whole directory unreadable.
- A missing or empty directory returns [].
- `scan_build` never raises.
'''


def main() -> None:
    result = cr.write_module(cr.CoderRuntime.CODEX, SPEC, workspace=WS,
                             path="build_scan.py", timeout=900.0)
    cr.record_call(result)
    print(f"ok={result.ok} seconds={result.seconds:.0f} "
          f"tokens={result.usage.get('total_tokens')} error={result.error[:150]}")


main()
