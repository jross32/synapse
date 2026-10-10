"""Publish a built, verified Synapse installer into the public download site.

Usage:
  python scripts/publish-synapse-download.py PATH_TO_TESTED_INSTALLER --platform windows --version 0.1.209

This copies an actual file and calculates SHA-256 from its bytes. It does not
sign or verify Windows installability: release approval remains a separate gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "download-site"
FORMATS = {"windows": ".exe", "macos": ".dmg", "linux": ".AppImage"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--platform", choices=FORMATS, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--verified", action="store_true", help="Confirms real installer smoke testing completed")
    args = parser.parse_args()
    if not args.verified:
        parser.error("Cannot publish before independent install/smoke verification. Pass --verified only after proof.")
    path = args.artifact.resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != FORMATS[args.platform].lower():
        parser.error("Expected an actual installer file with the platform extension")
    if path.stat().st_size < 1024 * 1024:
        parser.error("Installer is unexpectedly small")
    if any(ch in args.version for ch in "/\\:"):
        parser.error("Invalid version")

    filename = "Synapse-" + args.version + "-" + args.platform + FORMATS[args.platform]
    release_dir = SITE / "releases"
    release_dir.mkdir(exist_ok=True)
    destination = release_dir / filename
    if destination.exists():
        parser.error("Refusing to overwrite an already published release")
    shutil.copy2(path, destination)
    digest = hashlib.sha256()
    with destination.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    manifest_path = SITE / "releases.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") != args.version:
        manifest = {"version": args.version, "channel": "stable", "artifacts": []}
    manifest["artifacts"] = [a for a in manifest["artifacts"] if a.get("platform") != args.platform]
    manifest["artifacts"].append({
        "platform": args.platform, "status": "ready",
        "url": "/releases/" + filename, "sha256": digest.hexdigest(),
        "size_bytes": destination.stat().st_size,
    })
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Published", destination.name, "SHA256", digest.hexdigest())


if __name__ == "__main__":
    main()
