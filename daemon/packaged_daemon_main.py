"""Bundled-entry wrapper for the packaged Synapse daemon."""

from __future__ import annotations

from synapse_daemon.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
