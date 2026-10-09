"""Install a generated image into the public Synapse download site.

Run from the Synapse repo once the bytes are on the same machine:
    python scripts/install_synapse_brain.py C:/path/to/brain.png

Keeps project confinement and provenance via Synapse's canonical import service.
Does not fetch ChatGPT sandbox paths or touch the private daemon.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "daemon"))
from synapse_daemon.image_imports import import_image_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Real PNG/JPEG/WebP file on this host")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error("Source file does not exist locally; sandbox paths from another runtime do not work.")
    destination = f"download-site/assets/synapse-brain{args.source.suffix.lower()}"
    outcome = import_image_file(
        project_root=ROOT,
        source_path=args.source,
        relative_path=destination,
        origin="chatgpt_generated_image_manual_handoff",
        overwrite=args.overwrite,
    )
    print(outcome)
    print(f"Next: update download-site/index.html to use /assets/{Path(destination).name}, verify locally and on public HTTPS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
