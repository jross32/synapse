"""Provider-neutral, project-scoped AI video planning and render-job orchestration.

Synapse deliberately exposes a minutes-long *video* capability rather than pretending a
provider can create a perfect five-minute clip in one request. A video plan is split into
3-10 second story beats. Beats sharing a continuity group are rendered as a stateful
multi-turn sequence (up to 40 seconds), so characters, motion and audio can persist. The
resulting continuity blocks are assembled locally into the requested project MP4.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import video_compositor, video_credentials, video_local
from .subprocess_utils import headless_creationflags

DEFAULT_PROVIDER = "local"
DEFAULT_GOOGLE_MODEL = "gemini-omni-1.1-flash"
MAX_VIDEO_SECONDS = 300
MIN_SHOT_SECONDS = 3
MAX_SHOT_SECONDS = 10
MAX_CONTINUITY_SECONDS = 40
_ALLOWED_ASPECT_RATIOS = {"16:9", "9:16"}
_ALLOWED_RESOLUTIONS = {"360p", "720p", "1080p", "4k"}
_ALLOWED_AUDIO_MODES = {"native", "silent"}


class VideoStudioError(ValueError):
    """A safe, user-facing Video Studio error with API semantics."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "video_studio.invalid",
        status: int = 422,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


def _provider() -> str:
    return os.getenv("SYNAPSE_VIDEO_PROVIDER", DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER


def _google_model() -> str:
    return os.getenv("SYNAPSE_GOOGLE_VIDEO_MODEL", DEFAULT_GOOGLE_MODEL).strip() or DEFAULT_GOOGLE_MODEL


def _safe_root(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise VideoStudioError(f"registered project path does not exist: {root}")
    return root


def _safe_project_path(root: Path, relative_path: str, *, suffixes: set[str] | None = None) -> Path:
    raw = str(relative_path or "").strip()
    if not raw:
        raise VideoStudioError("project-relative path is required")
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.drive:
        raise VideoStudioError("path must stay inside the registered project")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise VideoStudioError("path escapes the registered project") from exc
    if suffixes is not None and target.suffix.lower() not in suffixes:
        raise VideoStudioError(f"path extension must be one of: {', '.join(sorted(suffixes))}")
    return target


def _video_state_root(root: Path) -> Path:
    state = root / ".synapse" / "video-studio"
    state.mkdir(parents=True, exist_ok=True)
    return state


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VideoStudioError(
            f"could not read Video Studio state: {path.name}",
            code="video_studio.state_invalid",
            status=500,
        ) from exc
    if not isinstance(value, dict):
        raise VideoStudioError(
            f"Video Studio state is not an object: {path.name}",
            code="video_studio.state_invalid",
            status=500,
        )
    return value


def video_generation_status(storage: Any | None = None) -> dict[str, Any]:
    credentials = video_credentials.credential_status(storage)
    provider = _provider()
    assembler = video_compositor.assembly_status()
    local = video_local.local_backend_status()
    google_ready = bool(credentials["google"]["configured"])
    runway_ready = bool(credentials["runway"]["configured"])
    if provider == "local":
        provider_ready = bool(local["configured"])
        model = "synapse-local"
        credential_source = None
    elif provider == "google":
        provider_ready = google_ready
        model = _google_model()
        credential_source = credentials["google"].get("source")
    else:
        provider_ready = False
        model = None
        credential_source = None
    return {
        "capability": "video_generation",
        "configured": bool(provider_ready and assembler["configured"]),
        "provider": provider,
        "model": model,
        "credential_source": credential_source,
        "requires_cloud_api_key": provider != "local",
        "local": local,
        "providers": {
            "local": {
                "configured": bool(local["configured"]),
                "generative_ai_ready": bool(local["generative_ai_ready"]),
                "backend": local["backend"],
                "role": "default",
                "requires_api_key": False,
                "features": ["offline_render", "local_assembly", "local_model_adapter", "procedural_proof"],
            },
            "google": {
                "configured": google_ready,
                "model": _google_model(),
                "role": "optional_external_adapter",
                "requires_api_key": True,
            },
            "runway": {
                "configured": runway_ready,
                "role": "optional_external_adapter",
                "requires_api_key": True,
            },
        },
        "assembler": assembler,
        "supports": {
            "max_video_seconds": MAX_VIDEO_SECONDS,
            "shot_seconds": {"min": MIN_SHOT_SECONDS, "max": MAX_SHOT_SECONDS},
            "continuity_group_seconds": MAX_CONTINUITY_SECONDS,
            "aspect_ratios": sorted(_ALLOWED_ASPECT_RATIOS),
            "resolutions": ["360p", "720p", "1080p", "4k"],
            "audio_modes": sorted(_ALLOWED_AUDIO_MODES),
            "native_audio": True,
            "dialogue": True,
            "reference_images": True,
            "story_bible": True,
            "character_bible": True,
            "detached_render_jobs": True,
            "targeted_shot_retry": True,
            "project_scoped_output": True,
            "asset_manifest": True,
        },
        "reason": None if provider_ready and assembler["configured"] else "The selected local/provider video engine is not ready.",
    }


def _normalize_shot(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise VideoStudioError(f"shot {index + 1} must be an object")
    prompt = str(raw.get("prompt") or "").strip()
    if not prompt:
        raise VideoStudioError(f"shot {index + 1} prompt is required")
    if len(prompt) > 12_000:
        raise VideoStudioError(f"shot {index + 1} prompt is too long")
    try:
        duration = int(raw.get("duration_seconds", 8))
    except (TypeError, ValueError) as exc:
        raise VideoStudioError(f"shot {index + 1} duration_seconds must be an integer") from exc
    if duration < MIN_SHOT_SECONDS or duration > MAX_SHOT_SECONDS:
        raise VideoStudioError(
            f"shot {index + 1} duration_seconds must be {MIN_SHOT_SECONDS}-{MAX_SHOT_SECONDS}"
        )
    continuity_group = str(raw.get("continuity_group") or f"scene-{index + 1}").strip()
    if not continuity_group or len(continuity_group) > 120:
        raise VideoStudioError(f"shot {index + 1} continuity_group must be 1-120 characters")
    dialogue = str(raw.get("dialogue") or "").strip()
    audio_cues = str(raw.get("audio_cues") or "").strip()
    transition = str(raw.get("transition") or "cut").strip()
    bridge_from_previous = bool(raw.get("bridge_from_previous", False))
    return {
        "index": index,
        "prompt": prompt,
        "duration_seconds": duration,
        "continuity_group": continuity_group,
        "dialogue": dialogue[:4_000] or None,
        "audio_cues": audio_cues[:4_000] or None,
        "transition": transition[:200] or "cut",
        "bridge_from_previous": bridge_from_previous,
    }


def _validate_reference_paths(root: Path, reference_paths: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in reference_paths or []:
        target = _safe_project_path(root, str(raw), suffixes={".png", ".jpg", ".jpeg", ".webp"})
        if not target.is_file():
            raise VideoStudioError(f"reference image does not exist: {raw}")
        normalized.append(target.relative_to(root).as_posix())
    if len(normalized) > 14:
        raise VideoStudioError("at most 14 reference images are supported per plan")
    return normalized


def create_video_plan(
    storage: Any,
    *,
    project_id: str,
    title: str,
    brief: str,
    shots: list[dict[str, Any]],
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    audio_mode: str = "native",
    story_bible: str = "",
    character_bible: str = "",
    style_bible: str = "",
    reference_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Validate and persist a deterministic long-form video storyboard."""
    from . import projects as projects_module

    clean_project_id = str(project_id or "").strip()
    if not clean_project_id:
        raise VideoStudioError("project_id is required")
    project = projects_module.get(storage.conn, clean_project_id)
    root = _safe_root(project.path)

    clean_title = str(title or "").strip()
    clean_brief = str(brief or "").strip()
    if not clean_title:
        raise VideoStudioError("title is required")
    if not clean_brief:
        raise VideoStudioError("brief is required")
    if len(clean_title) > 300 or len(clean_brief) > 32_000:
        raise VideoStudioError("title or brief is too long")
    if aspect_ratio not in _ALLOWED_ASPECT_RATIOS:
        raise VideoStudioError("aspect_ratio must be 16:9 or 9:16")
    if resolution not in _ALLOWED_RESOLUTIONS:
        raise VideoStudioError(f"resolution must be one of: {', '.join(sorted(_ALLOWED_RESOLUTIONS))}")
    if audio_mode not in _ALLOWED_AUDIO_MODES:
        raise VideoStudioError(f"audio_mode must be one of: {', '.join(sorted(_ALLOWED_AUDIO_MODES))}")
    if not shots:
        raise VideoStudioError("at least one shot is required")

    normalized_shots = [_normalize_shot(item, idx) for idx, item in enumerate(shots)]
    total_seconds = sum(int(item["duration_seconds"]) for item in normalized_shots)
    if total_seconds > MAX_VIDEO_SECONDS:
        raise VideoStudioError(f"planned duration exceeds {MAX_VIDEO_SECONDS} seconds")

    group_seconds: dict[str, int] = defaultdict(int)
    seen_groups: set[str] = set()
    last_group: str | None = None
    for shot in normalized_shots:
        group = str(shot["continuity_group"])
        group_seconds[group] += int(shot["duration_seconds"])
        if group != last_group:
            if group in seen_groups:
                raise VideoStudioError(
                    f"continuity_group '{group}' is non-contiguous; keep each continuity group in one block"
                )
            seen_groups.add(group)
            last_group = group
    too_long = {name: seconds for name, seconds in group_seconds.items() if seconds > MAX_CONTINUITY_SECONDS}
    if too_long:
        detail = ", ".join(f"{name}={seconds}s" for name, seconds in sorted(too_long.items()))
        raise VideoStudioError(
            f"continuity groups must be <= {MAX_CONTINUITY_SECONDS}s for stateful coherence: {detail}"
        )

    references = _validate_reference_paths(root, reference_paths)
    plan_id = uuid.uuid4().hex[:16]
    now = datetime.now(UTC).isoformat()
    plan = {
        "schema_version": 1,
        "plan_id": plan_id,
        "project_id": clean_project_id,
        "created_at": now,
        "title": clean_title,
        "brief": clean_brief,
        "provider": _provider(),
        "model": (_google_model() if _provider() == "google" else "synapse-local"),
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "audio_mode": audio_mode,
        "story_bible": str(story_bible or "").strip()[:32_000],
        "character_bible": str(character_bible or "").strip()[:32_000],
        "style_bible": str(style_bible or "").strip()[:32_000],
        "reference_paths": references,
        "shots": normalized_shots,
        "planned_duration_seconds": total_seconds,
        "continuity_groups": dict(group_seconds),
    }
    path = _video_state_root(root) / "plans" / f"{plan_id}.json"
    _write_json_atomic(path, plan)
    return {"created": True, "plan_path": str(path), **plan}


def get_video_plan(storage: Any, *, project_id: str, plan_id: str) -> dict[str, Any]:
    from . import projects as projects_module

    project = projects_module.get(storage.conn, str(project_id or "").strip())
    root = _safe_root(project.path)
    clean_plan_id = str(plan_id or "").strip()
    if not clean_plan_id or not clean_plan_id.isalnum():
        raise VideoStudioError("plan_id is invalid")
    path = _video_state_root(root) / "plans" / f"{clean_plan_id}.json"
    if not path.is_file():
        raise VideoStudioError("video plan not found", code="video_plan.not_found", status=404)
    return {"plan_path": str(path), **_read_json(path)}


def _job_path(root: Path, job_id: str) -> Path:
    return _video_state_root(root) / "jobs" / f"{job_id}.json"


def start_video_render(
    storage: Any,
    *,
    project_id: str,
    plan_id: str,
    relative_path: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Start a detached provider render job and immediately return its durable receipt."""
    from . import projects as projects_module

    clean_project_id = str(project_id or "").strip()
    project = projects_module.get(storage.conn, clean_project_id)
    root = _safe_root(project.path)
    plan = get_video_plan(storage, project_id=clean_project_id, plan_id=plan_id)
    output = _safe_project_path(root, relative_path, suffixes={".mp4"})
    if output.exists() and not overwrite:
        raise VideoStudioError(
            f"refusing to overwrite existing video: {output.relative_to(root).as_posix()}; pass overwrite=true",
            code="video_asset.conflict",
            status=409,
        )

    status = video_generation_status(storage)
    if not status["configured"]:
        raise VideoStudioError(
            str(status.get("reason") or "video generation is not configured"),
            code="video_generation.not_configured",
            status=503,
        )

    job_id = uuid.uuid4().hex[:16]
    job_dir = _video_state_root(root) / "renders" / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    job = {
        "schema_version": 1,
        "job_id": job_id,
        "project_id": clean_project_id,
        "plan_id": str(plan["plan_id"]),
        "status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "relative_path": output.relative_to(root).as_posix(),
        "overwrite": bool(overwrite),
        "planned_duration_seconds": plan["planned_duration_seconds"],
        "shot_count": len(plan["shots"]),
        "completed_shots": 0,
        "completed_groups": 0,
        "current_group": None,
        "current_shot": None,
        "error": None,
        "pid": None,
    }
    path = _job_path(root, job_id)
    _write_json_atomic(path, job)

    command = [
        sys.executable,
        "-m",
        "synapse_daemon.video_worker",
        "--data-dir",
        str(storage.data_dir),
        "--project-id",
        clean_project_id,
        "--job-id",
        job_id,
    ]
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=(job_dir / "worker.out.log").open("ab"),
            stderr=(job_dir / "worker.err.log").open("ab"),
            creationflags=headless_creationflags(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            ),
        )
    except OSError as exc:
        job.update(
            status="error",
            updated_at=datetime.now(UTC).isoformat(),
            error={"code": "video_worker.spawn_failed", "message": type(exc).__name__},
        )
        _write_json_atomic(path, job)
        raise VideoStudioError(
            f"could not start video worker: {type(exc).__name__}",
            code="video_worker.spawn_failed",
            status=500,
        ) from exc

    job["pid"] = proc.pid
    job["status"] = "starting"
    job["updated_at"] = datetime.now(UTC).isoformat()
    _write_json_atomic(path, job)
    return {"started": True, "job_path": str(path), **job}


def get_video_job(storage: Any, *, project_id: str, job_id: str) -> dict[str, Any]:
    from . import projects as projects_module

    project = projects_module.get(storage.conn, str(project_id or "").strip())
    root = _safe_root(project.path)
    clean_job_id = str(job_id or "").strip()
    if not clean_job_id or not clean_job_id.isalnum():
        raise VideoStudioError("job_id is invalid")
    path = _job_path(root, clean_job_id)
    if not path.is_file():
        raise VideoStudioError("video render job not found", code="video_job.not_found", status=404)
    return {"job_path": str(path), **_read_json(path)}


def cancel_video_render(storage: Any, *, project_id: str, job_id: str) -> dict[str, Any]:
    from . import projects as projects_module

    project = projects_module.get(storage.conn, str(project_id or "").strip())
    root = _safe_root(project.path)
    job = get_video_job(storage, project_id=project_id, job_id=job_id)
    if job.get("status") in {"completed", "error", "cancelled"}:
        return {"cancel_requested": False, **job}
    cancel_path = _video_state_root(root) / "renders" / str(job["job_id"]) / "CANCEL"
    cancel_path.parent.mkdir(parents=True, exist_ok=True)
    cancel_path.write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    return {"cancel_requested": True, **job}
