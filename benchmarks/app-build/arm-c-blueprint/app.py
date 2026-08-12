"""Entry point for the blueprint-built Trailmark (Arm C).

Thin on purpose. storage, passwords and pages were written by a local model and passed their
own contract and acceptance checks; api was escalated to Claude. Keeping the wiring in its own
file leaves that split of authorship visible instead of blending it into one artefact.
"""

from __future__ import annotations

import argparse

import storage
from api import app


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Trailmark.")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    storage.init_db()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
