"""Entry point: ``python -m synapse_daemon`` (or ``synapsed`` console script).

Milestone A — placeholder that prints version and exits.
Milestone B — replace with FastAPI/uvicorn boot on port 7878.
"""

from __future__ import annotations

import sys

from . import __version__


def main() -> int:
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"synapse-daemon {__version__}")
        return 0

    print(
        f"synapse-daemon {__version__} (scaffolding only — daemon comes online in Milestone B).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
