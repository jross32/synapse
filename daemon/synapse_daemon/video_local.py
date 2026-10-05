"""Local-first rendering backend for Synapse Video Studio.

This module exists so Synapse can be the AI-facing video API without requiring a cloud
video provider. The always-available procedural renderer is a deterministic smoke/proof
backend. Higher-fidelity local model engines (WanGP/ComfyUI/etc.) plug in behind the same
contract and may be selected when installed on the host.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from . import video_compositor

_SAFE_TEXT_RE = re.compile(r"[^A-Za-z0-9 .,_-]+")


def _candidate_wangp_roots() -> list[Path]:
    configured = os.getenv("SYNAPSE_WANGP_ROOT", "").strip()
    roots: list[Path] = []
    if configured:
        roots.append(Path(configured).expanduser())
    home = Path.home()
    roots.extend([home / "Wan2GP", home / "WanGP", home / "wangp"])
    return roots


def wangp_root() -> Path | None:
    for candidate in _candidate_wangp_roots():
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if (resolved / "wgp.py").is_file():
            return resolved
    return None


def local_backend_status() -> dict[str, Any]:
    """Report local rendering readiness without any internet/provider request."""
    assembler = video_compositor.assembly_status()
    root = wangp_root()
    selected = os.getenv("SYNAPSE_LOCAL_VIDEO_BACKEND", "auto").strip().lower() or "auto"
    if selected == "auto":
        backend = "wangp" if root else "procedural"
    else:
        backend = selected
    wangp_installed = root is not None
    # Presence of the source checkout alone does not prove model weights/dependencies are ready.
    # We expose it separately instead of falsely claiming production generative readiness.
    generative_ready = bool(
        backend == "wangp"
        and wangp_installed
        and os.getenv("SYNAPSE_WANGP_READY", "").strip().lower() in {"1", "true", "yes", "on"}
    )
    return {
        "provider": "local",
        "backend": backend,
        "configured": bool(assembler.get("configured")),
        "generative_ai_ready": generative_ready,
        "procedural_ready": bool(assembler.get("configured")),
        "wangp": {
            "installed": wangp_installed,
            "root": str(root) if root else None,
            "ready": generative_ready,
            "note": (
                "WanGP source detected and explicitly marked ready."
                if generative_ready
                else "WanGP is optional; install/configure local model weights to enable photorealistic generative rendering."
            ),
        },
        "assembler": assembler,
        "requires_cloud_api_key": False,
    }


def _safe_overlay_text(text: str, *, max_chars: int = 72) -> str:
    clean = _SAFE_TEXT_RE.sub(" ", str(text or "")).replace(":", " ")
    clean = " ".join(clean.split())
    return clean[:max_chars] or "SYNAPSE LOCAL VIDEO"


def generate_procedural_clip(
    *,
    prompt: str,
    duration_seconds: int,
    target: str | Path,
    scene_index: int = 0,
    audio: bool = True,
) -> Path:
    """Create a real MP4 entirely locally for smoke/proof/fallback workflows.

    This is deliberately labeled procedural; callers must not present it as a diffusion/
    generative-model result. It proves the no-cloud render/assembly path and gives Synapse a
    deterministic backend for tests even when large model weights are absent.
    """
    target_path = Path(target).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = video_compositor.ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("local video renderer is unavailable because ffmpeg is not configured")

    digest = hashlib.sha256(f"{prompt}|{scene_index}".encode()).hexdigest()
    colors = ["0x101820", "0x1b4332", "0x2b2d42", "0x3d405b", "0x14213d", "0x242423"]
    accents = ["0x3a86ff", "0x52b788", "0xef233c", "0xf4a261", "0x9b5de5", "0x00b4d8"]
    color = colors[int(digest[:2], 16) % len(colors)]
    accent = accents[int(digest[2:4], 16) % len(accents)]
    tone = 180 + (int(digest[4:8], 16) % 420)
    label = _safe_overlay_text(prompt)
    font = "C\\:/Windows/Fonts/arial.ttf"
    vf = (
        f"drawbox=x='80+mod(t*220,900)':y='230+sin(t*1.8)*90':w=190:h=190:color={accent}:t=fill,"
        f"drawtext=fontfile='{font}':text='SYNAPSE LOCAL':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=80,"
        f"drawtext=fontfile='{font}':text='{label}':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=610"
    )
    args = [
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=1280x720:d={int(duration_seconds)}:r=30",
    ]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency={tone}:duration={int(duration_seconds)}:sample_rate=48000"]
    args += ["-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast"]
    if audio:
        args += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    else:
        args += ["-an"]
    args.append(str(target_path))

    result = video_compositor._run(args, timeout=max(120.0, duration_seconds * 15.0))
    if result.returncode != 0 or not target_path.is_file() or target_path.stat().st_size == 0:
        detail = (result.stderr or result.stdout or "local ffmpeg render failed")[-1200:]
        raise RuntimeError(f"local procedural video render failed: {detail}")
    return target_path
