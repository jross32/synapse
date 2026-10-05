"""Detached renderer for Synapse Video Studio.

The worker renders short Gemini Omni clips in continuity groups. Within a group it uses
`previous_interaction_id` extension, keeping the current cumulative group video and audio
coherent. Across groups it supplies the preceding block's last frame plus the plan's fixed
reference images, then assembles all final blocks locally into one MP4.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from . import projects as projects_module
from . import video_assets, video_compositor, video_credentials, video_local
from .audit import AuditRecord, audit
from .storage import Storage

_GOOGLE_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_GOOGLE_FILES_URL = "https://generativelanguage.googleapis.com/v1beta/files"
_FILE_ID_RE = re.compile(r"/files/([^/:?]+)")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_job(path: Path, job: dict[str, Any], **updates: Any) -> None:
    job.update(updates)
    job["updated_at"] = _now()
    video_assets._write_json_atomic(path, job)  # same project-local atomic-state primitive


def _provider_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or "").strip()
                code = str(error.get("status") or error.get("code") or "").strip()
                if code and message:
                    return f"{code}: {message[:500]}"
                if message:
                    return message[:500]
    except Exception:  # noqa: BLE001 - error parsing must not hide HTTP status
        pass
    return f"Google video request failed with HTTP {response.status_code}"


def _video_content(body: dict[str, Any]) -> dict[str, Any] | None:
    direct = body.get("output_video")
    if isinstance(direct, dict) and (direct.get("data") or direct.get("uri")):
        return direct
    for step in reversed(body.get("steps") or []):
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for item in reversed(step.get("content") or []):
            if isinstance(item, dict) and item.get("type") == "video" and (item.get("data") or item.get("uri")):
                return item
    return None


def _poll_and_download_uri(client: httpx.Client, *, uri: str, api_key: str, target: Path) -> None:
    match = _FILE_ID_RE.search(uri)
    if not match:
        raise RuntimeError("provider returned a video URI without a Files API id")
    file_id = match.group(1)
    deadline = time.monotonic() + 1_800
    while True:
        response = client.get(
            f"{_GOOGLE_FILES_URL}/{quote(file_id, safe='')}?key={quote(api_key, safe='')}",
            timeout=60.0,
        )
        if response.status_code >= 400:
            raise RuntimeError(_provider_error(response))
        payload = response.json()
        state_value = payload.get("state") if isinstance(payload, dict) else None
        if isinstance(state_value, dict):
            state = str(state_value.get("name") or "").upper()
        else:
            state = str(state_value or "").upper()
        if state == "ACTIVE":
            break
        if state == "FAILED":
            raise RuntimeError("provider video file entered FAILED state")
        if time.monotonic() >= deadline:
            raise RuntimeError("timed out waiting for provider video file to become ACTIVE")
        time.sleep(5)

    response = client.get(
        f"{_GOOGLE_FILES_URL}/{quote(file_id, safe='')}:download",
        params={"alt": "media", "key": api_key},
        timeout=300.0,
        follow_redirects=True,
    )
    if response.status_code >= 400:
        raise RuntimeError(_provider_error(response))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)


def _save_output_video(
    client: httpx.Client,
    *,
    body: dict[str, Any],
    api_key: str,
    target: Path,
) -> None:
    video = _video_content(body)
    if not video:
        raise RuntimeError("provider returned no video output")
    encoded = video.get("data")
    if encoded:
        try:
            payload = base64.b64decode(str(encoded), validate=True)
        except ValueError as exc:
            raise RuntimeError("provider returned invalid base64 video data") from exc
        if not payload:
            raise RuntimeError("provider returned an empty video")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return
    uri = str(video.get("uri") or "").strip()
    if uri:
        _poll_and_download_uri(client, uri=uri, api_key=api_key, target=target)
        return
    raise RuntimeError("provider video output has neither data nor uri")


def _reference_input(root: Path, references: list[str], continuity_frame: Path | None) -> tuple[list[dict[str, Any]], str]:
    inputs: list[dict[str, Any]] = []
    declarations: list[str] = []
    image_number = 1

    if continuity_frame is not None and continuity_frame.is_file():
        data = base64.b64encode(continuity_frame.read_bytes()).decode("ascii")
        inputs.append({"type": "image", "data": data, "mime_type": "image/png"})
        declarations.append(f"[# Sources <FIRST_FRAME>@Image{image_number}]")
        image_number += 1

    for ref_index, relative in enumerate(references):
        path = (root / relative).resolve()
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        inputs.append({"type": "image", "data": data, "mime_type": mime})
        declarations.append(f"[# References <IMAGE_REF_{ref_index}>@Image{image_number}]")
        image_number += 1

    return inputs, " ".join(declarations)


def _shot_prompt(plan: dict[str, Any], shot: dict[str, Any], *, is_extension: bool, declarations: str = "") -> str:
    parts = []
    if declarations:
        parts.append(declarations)
    parts.extend(
        [
            "Create this as one coherent part of a longer Synapse-directed film.",
            "Preserve identity, facial features, body proportions, wardrobe, props, environment logic, lighting logic, and spatial continuity unless the shot explicitly changes them.",
            f"FILM BRIEF: {plan['brief']}",
        ]
    )
    if plan.get("story_bible"):
        parts.append(f"STORY BIBLE: {plan['story_bible']}")
    if plan.get("character_bible"):
        parts.append(f"CHARACTER BIBLE: {plan['character_bible']}")
    if plan.get("style_bible"):
        parts.append(f"VISUAL STYLE BIBLE: {plan['style_bible']}")
    if is_extension:
        parts.append(
            "EXTENSION RULE: Extend the previous generated video seamlessly. Keep the same characters, motion, scene state, and audio state. Do not restart the action."
        )
    else:
        parts.append("SHOT RULE: Use a single continuous cinematic scene unless a cut is explicitly requested below.")
    parts.append(f"SHOT: {shot['prompt']}")
    if shot.get("dialogue"):
        parts.append(f"SPOKEN DIALOGUE (use these words naturally): {shot['dialogue']}")
    if shot.get("audio_cues"):
        parts.append(f"AUDIO / SOUND CUES: {shot['audio_cues']}")
    if plan.get("audio_mode") == "silent":
        parts.append("AUDIO RULE: Silent video. No speech, music, ambience, or sound effects.")
    else:
        parts.append(
            "AUDIO RULE: Generate coherent native audio for this shot. Keep recurring voices acoustically consistent across this continuity group; preserve ambience and music across extensions unless directed otherwise."
        )
    parts.append(f"TRANSITION INTENT: {shot.get('transition') or 'cut'}")
    return "\n\n".join(parts)


def _generate_turn(
    client: httpx.Client,
    *,
    api_key: str,
    model: str,
    plan: dict[str, Any],
    shot: dict[str, Any],
    target: Path,
    previous_interaction_id: str | None,
    root: Path,
    continuity_frame: Path | None,
) -> str:
    is_extension = bool(previous_interaction_id)
    media_inputs: list[dict[str, Any]] = []
    declarations = ""
    if not is_extension:
        media_inputs, declarations = _reference_input(root, plan.get("reference_paths") or [], continuity_frame)
    prompt = _shot_prompt(plan, shot, is_extension=is_extension, declarations=declarations)
    request_input: Any = prompt
    if media_inputs:
        request_input = [*media_inputs, {"type": "text", "text": prompt}]

    response_format = {
        "type": "video",
        "aspect_ratio": plan["aspect_ratio"],
        "resolution": plan["resolution"],
        "duration": f"{shot['duration_seconds']}s",
        "delivery": "uri" if plan["resolution"] in {"1080p", "4k"} else "inline",
    }
    payload: dict[str, Any] = {
        "model": model,
        "input": request_input,
        "response_format": response_format,
        "background": False,
        "stream": False,
        # Required for previous_interaction_id stateful extension in later turns.
        "store": True,
    }
    if previous_interaction_id:
        payload["previous_interaction_id"] = previous_interaction_id
        # Prompting is primary, but explicit extend makes the intended multi-turn behavior unambiguous.
        payload["generation_config"] = {"video_config": {"task": "extend"}}

    response = client.post(
        _GOOGLE_INTERACTIONS_URL,
        params={"key": api_key},
        json=payload,
        timeout=900.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(_provider_error(response))
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError("provider returned a non-object interaction")
    interaction_id = str(body.get("id") or "").strip()
    if not interaction_id:
        raise RuntimeError("provider returned no interaction id")
    _save_output_video(client, body=body, api_key=api_key, target=target)
    return interaction_id


def _append_manifest(
    root: Path,
    *,
    final_path: Path,
    plan: dict[str, Any],
    job: dict[str, Any],
    actual_duration: float | None,
) -> Path:
    manifest = root / ".synapse" / "video-assets.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "kind": "generated_video",
        "created_at": _now(),
        "path": final_path.relative_to(root).as_posix(),
        "plan_id": plan["plan_id"],
        "job_id": job["job_id"],
        "provider": plan["provider"],
        "model": plan["model"],
        "aspect_ratio": plan["aspect_ratio"],
        "resolution": plan["resolution"],
        "audio_mode": plan["audio_mode"],
        "planned_duration_seconds": plan["planned_duration_seconds"],
        "actual_duration_seconds": actual_duration,
        "shot_count": len(plan["shots"]),
        "continuity_group_count": len(plan["continuity_groups"]),
        "reference_paths": plan.get("reference_paths") or [],
        "sha256": _sha256(final_path),
        "bytes": final_path.stat().st_size,
    }
    with manifest.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return manifest



def _run_local_job(
    storage: Storage,
    *,
    project_id: str,
    root: Path,
    job_path: Path,
    job: dict[str, Any],
    plan: dict[str, Any],
    render_dir: Path,
    cancel_path: Path,
    output: Path,
) -> None:
    """Render a plan entirely on the local machine without any cloud API key."""
    local = video_local.local_backend_status()
    if not local.get("configured"):
        raise RuntimeError("Synapse local video engine is not configured")

    backend = str(local.get("backend") or "procedural")
    # Until a local generative model runtime is marked ready, use the explicit procedural
    # proof backend. This is never mislabeled as diffusion/photorealistic generation.
    if backend != "procedural" and not local.get("generative_ai_ready"):
        backend = "procedural"

    _write_job(
        job_path,
        job,
        status="rendering",
        credential_source=None,
        render_provider="local",
        render_backend=backend,
        generative_ai=bool(local.get("generative_ai_ready") and backend != "procedural"),
        started_at=_now(),
    )

    clips: list[Path] = []
    shots = list(plan["shots"])
    for position, shot in enumerate(shots):
        if cancel_path.exists():
            _write_job(job_path, job, status="cancelled", cancelled_at=_now())
            return
        shot_index = int(shot["index"])
        target = render_dir / f"local-shot-{shot_index + 1:03d}.mp4"
        _write_job(
            job_path,
            job,
            status="rendering",
            current_group=shot.get("continuity_group"),
            current_shot=shot_index,
            current_prompt_summary=str(shot["prompt"])[:240],
        )

        if backend == "procedural":
            video_local.generate_procedural_clip(
                prompt=str(shot["prompt"]),
                duration_seconds=int(shot["duration_seconds"]),
                target=target,
                scene_index=position,
                audio=plan.get("audio_mode") != "silent",
            )
        else:
            raise RuntimeError(
                f"local generative backend '{backend}' is marked ready but its Synapse adapter is not implemented"
            )
        clips.append(target)
        _write_job(
            job_path,
            job,
            completed_shots=position + 1,
            completed_groups=len({str(item.get("continuity_group")) for item in shots[: position + 1]}),
            latest_preview_path=target.relative_to(root).as_posix(),
        )

    if cancel_path.exists():
        _write_job(job_path, job, status="cancelled", cancelled_at=_now())
        return

    _write_job(job_path, job, status="assembling", current_group=None, current_shot=None)
    assembly = video_compositor.concatenate_clips(clips, output, overwrite=bool(job.get("overwrite")))
    actual_duration = assembly.get("duration_seconds")
    manifest = _append_manifest(root, final_path=output, plan=plan, job=job, actual_duration=actual_duration)

    with storage.transaction() as conn:
        audit(
            conn,
            AuditRecord(
                entity_type="video_asset",
                entity_id=f"{project_id}:{output.relative_to(root).as_posix()}",
                action="generate",
                source="video-studio-local-worker",
                result="success",
                details={
                    "project_id": project_id,
                    "project_relative_path": output.relative_to(root).as_posix(),
                    "plan_id": plan["plan_id"],
                    "job_id": job["job_id"],
                    "provider": "local",
                    "backend": backend,
                    "generative_ai": bool(local.get("generative_ai_ready") and backend != "procedural"),
                    "bytes": output.stat().st_size,
                    "sha256": _sha256(output),
                    "planned_duration_seconds": plan["planned_duration_seconds"],
                    "actual_duration_seconds": actual_duration,
                },
            ),
        )

    _write_job(
        job_path,
        job,
        status="completed",
        completed_at=_now(),
        current_group=None,
        current_shot=None,
        output_path=output.relative_to(root).as_posix(),
        absolute_output_path=str(output),
        bytes=output.stat().st_size,
        sha256=_sha256(output),
        actual_duration_seconds=actual_duration,
        manifest_path=str(manifest),
        render_provider="local",
        render_backend=backend,
        generative_ai=bool(local.get("generative_ai_ready") and backend != "procedural"),
    )

def run_job(*, data_dir: Path, project_id: str, job_id: str) -> None:
    storage = Storage(data_dir)
    storage.open()
    try:
        project = projects_module.get(storage.conn, project_id)
        root = Path(project.path).expanduser().resolve()
        job_path = root / ".synapse" / "video-studio" / "jobs" / f"{job_id}.json"
        job = video_assets._read_json(job_path)
        plan = video_assets.get_video_plan(storage, project_id=project_id, plan_id=str(job["plan_id"]))
        render_dir = root / ".synapse" / "video-studio" / "renders" / job_id
        cancel_path = render_dir / "CANCEL"
        output = video_assets._safe_project_path(root, str(job["relative_path"]), suffixes={".mp4"})

        provider = str(plan.get("provider") or "local")
        if provider == "local":
            _run_local_job(
                storage,
                project_id=project_id,
                root=root,
                job_path=job_path,
                job=job,
                plan=plan,
                render_dir=render_dir,
                cancel_path=cancel_path,
                output=output,
            )
            return

        if provider != "google":
            raise RuntimeError(f"provider adapter is not implemented: {provider}")
        api_key, credential_source = video_credentials.resolve_google_api_key(storage)
        if not api_key:
            raise RuntimeError("Google/Gemini video API credential is no longer configured")

        _write_job(
            job_path,
            job,
            status="rendering",
            credential_source=credential_source,
            started_at=_now(),
        )

        final_blocks: list[Path] = []
        continuity_frame: Path | None = None
        shots = list(plan["shots"])
        group_names: list[str] = []
        for shot in shots:
            if not group_names or group_names[-1] != shot["continuity_group"]:
                group_names.append(str(shot["continuity_group"]))

        completed_shots = 0
        for group_index, group_name in enumerate(group_names):
            group_shots = [shot for shot in shots if shot["continuity_group"] == group_name]
            previous_interaction_id: str | None = None
            current_cumulative: Path | None = None

            for local_index, shot in enumerate(group_shots):
                if cancel_path.exists():
                    _write_job(job_path, job, status="cancelled", cancelled_at=_now())
                    return
                shot_index = int(shot["index"])
                target = render_dir / f"group-{group_index + 1:02d}-turn-{local_index + 1:02d}-shot-{shot_index + 1:03d}.mp4"
                _write_job(
                    job_path,
                    job,
                    status="rendering",
                    current_group=group_name,
                    current_shot=shot_index,
                    current_prompt_summary=str(shot["prompt"])[:240],
                )
                previous_interaction_id = _generate_turn(
                    http_client,
                    api_key=api_key,
                    model=str(plan["model"]),
                    plan=plan,
                    shot=shot,
                    target=target,
                    previous_interaction_id=previous_interaction_id,
                    root=root,
                    continuity_frame=continuity_frame if local_index == 0 else None,
                )
                current_cumulative = target
                completed_shots += 1
                _write_job(
                    job_path,
                    job,
                    completed_shots=completed_shots,
                    interaction_id=previous_interaction_id,
                    latest_preview_path=target.relative_to(root).as_posix(),
                )

            if current_cumulative is None:
                raise RuntimeError(f"continuity group produced no video: {group_name}")
            final_blocks.append(current_cumulative)
            _write_job(
                job_path,
                job,
                completed_groups=group_index + 1,
                latest_block_path=current_cumulative.relative_to(root).as_posix(),
            )

            if group_index < len(group_names) - 1:
                next_group_name = group_names[group_index + 1]
                next_group_shots = [shot for shot in shots if shot["continuity_group"] == next_group_name]
                if next_group_shots and bool(next_group_shots[0].get("bridge_from_previous")):
                    continuity_frame = render_dir / f"continuity-{group_index + 1:02d}.png"
                    video_compositor.extract_last_frame(current_cumulative, continuity_frame)
                else:
                    continuity_frame = None

        if cancel_path.exists():
            _write_job(job_path, job, status="cancelled", cancelled_at=_now())
            return

        _write_job(job_path, job, status="assembling", current_group=None, current_shot=None)
        assembly = video_compositor.concatenate_clips(
            final_blocks,
            output,
            overwrite=bool(job.get("overwrite")),
        )
        actual_duration = assembly.get("duration_seconds")
        manifest = _append_manifest(
            root,
            final_path=output,
            plan=plan,
            job=job,
            actual_duration=actual_duration,
        )

        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="video_asset",
                    entity_id=f"{project_id}:{output.relative_to(root).as_posix()}",
                    action="generate",
                    source="video-studio-worker",
                    result="success",
                    details={
                        "project_id": project_id,
                        "project_relative_path": output.relative_to(root).as_posix(),
                        "plan_id": plan["plan_id"],
                        "job_id": job_id,
                        "provider": plan["provider"],
                        "model": plan["model"],
                        "bytes": output.stat().st_size,
                        "sha256": _sha256(output),
                        "planned_duration_seconds": plan["planned_duration_seconds"],
                        "actual_duration_seconds": actual_duration,
                    },
                ),
            )

        _write_job(
            job_path,
            job,
            status="completed",
            completed_at=_now(),
            current_group=None,
            current_shot=None,
            output_path=output.relative_to(root).as_posix(),
            absolute_output_path=str(output),
            bytes=output.stat().st_size,
            sha256=_sha256(output),
            actual_duration_seconds=actual_duration,
            manifest_path=str(manifest),
        )
    except Exception as exc:  # noqa: BLE001 - detached worker must persist a durable failure receipt
        try:
            project = projects_module.get(storage.conn, project_id)
            root = Path(project.path).expanduser().resolve()
            job_path = root / ".synapse" / "video-studio" / "jobs" / f"{job_id}.json"
            job = video_assets._read_json(job_path) if job_path.is_file() else {"job_id": job_id, "project_id": project_id}
            _write_job(
                job_path,
                job,
                status="error",
                failed_at=_now(),
                error={
                    "code": "video_render.failed",
                    "type": type(exc).__name__,
                    "message": str(exc)[:1000],
                },
            )
        except Exception:
            pass
        raise
    finally:
        storage.close()


# One client per detached worker lets HTTP keep-alive amortize 30+ sequential short-shot calls.
http_client = httpx.Client(follow_redirects=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synapse Video Studio detached renderer")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    try:
        run_job(data_dir=Path(args.data_dir), project_id=args.project_id, job_id=args.job_id)
        return 0
    finally:
        http_client.close()


if __name__ == "__main__":
    raise SystemExit(main())
