"""Local video assembly helpers for Synapse Video Studio.

Provider calls intentionally create short clips. This module turns those clips into one
project video, which is how Synapse can offer coherent minutes-long outputs while keeping
individual generations retryable. It prefers a system ffmpeg and otherwise uses the
`imageio-ffmpeg` bundled binary when that optional runtime dependency is installed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .subprocess_utils import headless_creationflags

_DURATION_RE = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")


class VideoCompositorError(ValueError):
    """A safe, user-facing local video assembly error."""


def ffmpeg_executable() -> str | None:
    configured = os.getenv("SYNAPSE_FFMPEG_PATH", "").strip()
    if configured and Path(configured).is_file():
        return configured
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        candidate = imageio_ffmpeg.get_ffmpeg_exe()
        if candidate and Path(candidate).is_file():
            return candidate
    except (ImportError, OSError):
        return None
    return None


def assembly_status() -> dict[str, Any]:
    executable = ffmpeg_executable()
    return {
        "configured": bool(executable),
        "engine": "ffmpeg" if executable else None,
        "executable": executable,
        "reason": None if executable else "ffmpeg is not available; install imageio-ffmpeg or set SYNAPSE_FFMPEG_PATH",
    }


def _run(args: list[str], *, timeout: float = 600.0) -> subprocess.CompletedProcess[str]:
    executable = ffmpeg_executable()
    if not executable:
        raise VideoCompositorError(
            "video assembly is not configured: ffmpeg is unavailable (install imageio-ffmpeg or set SYNAPSE_FFMPEG_PATH)"
        )
    try:
        return subprocess.run(
            [executable, *args],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            creationflags=headless_creationflags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoCompositorError("ffmpeg timed out while processing video") from exc
    except OSError as exc:
        raise VideoCompositorError(f"could not start ffmpeg: {type(exc).__name__}") from exc


def probe_duration(path: str | Path) -> float | None:
    target = Path(path).resolve()
    if not target.is_file():
        return None
    result = _run(["-hide_banner", "-i", str(target), "-f", "null", "-"], timeout=120.0)
    text = f"{result.stderr}\n{result.stdout}"
    match = _DURATION_RE.search(text)
    if not match:
        return None
    hours, minutes, seconds = int(match.group(1)), int(match.group(2)), float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def extract_last_frame(video_path: str | Path, output_path: str | Path) -> Path:
    source = Path(video_path).resolve()
    target = Path(output_path).resolve()
    if not source.is_file():
        raise VideoCompositorError(f"clip does not exist: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            "-y",
            "-sseof",
            "-0.08",
            "-i",
            str(source),
            "-frames:v",
            "1",
            str(target),
        ],
        timeout=120.0,
    )
    if result.returncode != 0 or not target.is_file():
        detail = (result.stderr or result.stdout or "ffmpeg failed")[-800:]
        raise VideoCompositorError(f"could not extract continuity frame: {detail}")
    return target


def concatenate_clips(
    clip_paths: list[str | Path],
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    clips = [Path(item).resolve() for item in clip_paths]
    if not clips:
        raise VideoCompositorError("at least one clip is required")
    for clip in clips:
        if not clip.is_file():
            raise VideoCompositorError(f"clip does not exist: {clip}")

    target = Path(output_path).resolve()
    if target.exists() and not overwrite:
        raise VideoCompositorError(f"refusing to overwrite existing video: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    def _concat_quote(path: Path) -> str:
        # ffmpeg concat demuxer uses single-quoted file syntax; escape an embedded quote.
        value = path.as_posix().replace("'", "'\\''")
        return f"file '{value}'"

    with tempfile.TemporaryDirectory(prefix="synapse-video-") as temp_dir:
        concat_file = Path(temp_dir) / "clips.txt"
        concat_file.write_text("\n".join(_concat_quote(path) for path in clips) + "\n", encoding="utf-8")
        result = _run(
            [
                "-y" if overwrite else "-n",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(target),
            ],
            timeout=max(600.0, 120.0 * len(clips)),
        )
    if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        detail = (result.stderr or result.stdout or "ffmpeg failed")[-1200:]
        raise VideoCompositorError(f"video assembly failed: {detail}")

    return {
        "path": str(target),
        "bytes": target.stat().st_size,
        "duration_seconds": probe_duration(target),
        "clip_count": len(clips),
        "engine": "ffmpeg",
    }
