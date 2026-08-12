"""Entry point for Trailmark (Arm B).

Thin by design: storage, passwords and pages were written by a local model, api was
escalated to Claude. This file just wires them together and serves them, so the split of
authorship stays visible rather than being blended into one file.
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
