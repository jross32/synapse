"""Allowlisted release manifest backing Synapse Downloads and Updates.

Only artifacts physically present in the published release directory are
shown as downloadable. Unsigned development builds in other directories
are not published accidentally.
"""
from __future__ import annotations

import hashlib
from pydantic import BaseModel, Field
from . import __version__
from .runtime_paths import repo_root


class ReleaseArtifact(BaseModel):
    platform: str
    label: str
    status: str
    format: str
    filename: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    download_url: str | None = None


class ReleaseManifest(BaseModel):
    version: str
    channel: str = "stable"
    artifacts: list[ReleaseArtifact] = Field(default_factory=list)


def _artifact(platform: str, label: str, fmt: str, filename: str) -> ReleaseArtifact:
    path = repo_root() / "release" / filename
    if path.is_file() and not path.is_symlink():
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        size = path.stat().st_size
        if size > 0:
            return ReleaseArtifact(
                platform=platform,
                label=label,
                status="ready",
                format=fmt,
                filename=filename,
                size_bytes=size,
                sha256=digest.hexdigest(),
                download_url=f"/api/v1/about/download/{filename}",
            )
    return ReleaseArtifact(platform=platform, label=label, status="planned", format=fmt)


def release_manifest() -> ReleaseManifest:
    return ReleaseManifest(
        version=__version__,
        artifacts=[
            _artifact("windows", "Windows 10/11 (64-bit)", "exe", f"Synapse Setup {__version__}.exe"),
            _artifact("macos", "macOS 12+ (Intel & Apple Silicon)", "dmg", f"Synapse-{__version__}.dmg"),
            _artifact("linux", "Linux (AppImage)", "AppImage", f"Synapse-{__version__}.AppImage"),
        ],
    )
