"""Focused tests for Synapse Video Studio orchestration contracts."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx
import pytest
from synapse_daemon import video_asset_catalog, video_assets, video_compositor, video_worker
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage


def _storage_with_project(tmp_path: Path) -> tuple[Storage, Path]:
    root = tmp_path / "project"
    root.mkdir()
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(conn, Project(id="demo", name="Demo", path=str(root), launch_cmd="echo hi"))
    return storage, root


def test_status_exposes_five_minute_coherence_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, _ = _storage_with_project(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(video_compositor, "assembly_status", lambda: {"configured": True, "engine": "ffmpeg"})

    status = video_assets.video_generation_status(storage)

    assert status["configured"] is True
    assert status["provider"] == "local"
    assert status["requires_cloud_api_key"] is False
    assert status["model"] == "gemini-omni-1.1-flash"
    assert status["supports"]["max_video_seconds"] == 300
    assert status["supports"]["continuity_group_seconds"] == 40
    assert status["supports"]["native_audio"] is True
    assert status["supports"]["dialogue"] is True
    storage.close()


def test_plan_persists_bibles_dialogue_and_reference_images(tmp_path: Path) -> None:
    storage, root = _storage_with_project(tmp_path)
    ref = root / "refs" / "hero.png"
    ref.parent.mkdir()
    ref.write_bytes(b"not-decoded-here")

    plan = video_assets.create_video_plan(
        storage,
        project_id="demo",
        title="The Walk Home",
        brief="One continuous emotional story with the same protagonist.",
        aspect_ratio="16:9",
        resolution="720p",
        audio_mode="native",
        story_bible="A clear beginning, escalation, and resolution.",
        character_bible="Mara: red coat, black hair, calm voice.",
        style_bible="Photorealistic cinematic natural light.",
        reference_paths=["refs/hero.png"],
        shots=[
            {
                "prompt": "Mara leaves the station and looks toward home.",
                "duration_seconds": 8,
                "continuity_group": "station",
                "dialogue": "I should have called sooner.",
                "audio_cues": "Distant train, soft city ambience.",
            },
            {
                "prompt": "She continues walking as rain begins.",
                "duration_seconds": 8,
                "continuity_group": "station",
            },
            {
                "prompt": "Cut to the same Mara arriving at her street.",
                "duration_seconds": 8,
                "continuity_group": "home-street",
            },
        ],
    )

    assert plan["planned_duration_seconds"] == 24
    assert plan["continuity_groups"] == {"station": 16, "home-street": 8}
    assert plan["shots"][0]["dialogue"] == "I should have called sooner."
    assert Path(plan["plan_path"]).is_file()
    loaded = video_assets.get_video_plan(storage, project_id="demo", plan_id=plan["plan_id"])
    assert loaded["character_bible"].startswith("Mara")
    assert loaded["reference_paths"] == ["refs/hero.png"]
    storage.close()


def test_plan_rejects_more_than_five_minutes(tmp_path: Path) -> None:
    storage, _ = _storage_with_project(tmp_path)
    shots = [
        {"prompt": f"Beat {i}", "duration_seconds": 10, "continuity_group": f"g{i}"}
        for i in range(31)
    ]
    with pytest.raises(video_assets.VideoStudioError, match="exceeds 300"):
        video_assets.create_video_plan(
            storage,
            project_id="demo",
            title="Too long",
            brief="test",
            shots=shots,
        )
    storage.close()


def test_plan_rejects_overlong_or_noncontiguous_continuity_group(tmp_path: Path) -> None:
    storage, _ = _storage_with_project(tmp_path)
    with pytest.raises(video_assets.VideoStudioError, match="<= 40s"):
        video_assets.create_video_plan(
            storage,
            project_id="demo",
            title="Too continuous",
            brief="test",
            shots=[
                {"prompt": f"Beat {i}", "duration_seconds": 10, "continuity_group": "same"}
                for i in range(5)
            ],
        )

    with pytest.raises(video_assets.VideoStudioError, match="non-contiguous"):
        video_assets.create_video_plan(
            storage,
            project_id="demo",
            title="Returns to old group",
            brief="test",
            shots=[
                {"prompt": "A", "duration_seconds": 8, "continuity_group": "one"},
                {"prompt": "B", "duration_seconds": 8, "continuity_group": "two"},
                {"prompt": "C", "duration_seconds": 8, "continuity_group": "one"},
            ],
        )
    storage.close()


def test_worker_parses_rest_steps_inline_video(tmp_path: Path) -> None:
    target = tmp_path / "clip.mp4"
    payload = b"mp4-test-bytes"
    body = {
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "video",
                        "mime_type": "video/mp4",
                        "data": base64.b64encode(payload).decode("ascii"),
                    }
                ],
            }
        ],
        "id": "v1_test",
    }
    video_worker._save_output_video(httpx.Client(), body=body, api_key="x", target=target)
    assert target.read_bytes() == payload


def test_extension_request_uses_previous_interaction_and_native_audio_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = httpx.Request("POST", "https://example.test")
    output = b"video-turn"
    response = httpx.Response(
        200,
        request=request,
        json={
            "id": "v1_next",
            "steps": [
                {
                    "type": "model_output",
                    "content": [
                        {"type": "video", "mime_type": "video/mp4", "data": base64.b64encode(output).decode("ascii")}
                    ],
                }
            ],
        },
    )
    seen: dict[str, object] = {}

    class FakeClient:
        def post(self, url, **kwargs):  # noqa: ANN001
            seen["url"] = url
            seen.update(kwargs)
            return response

    plan = {
        "brief": "A coherent story.",
        "story_bible": "Keep chronology.",
        "character_bible": "Same protagonist.",
        "style_bible": "Photorealistic.",
        "audio_mode": "native",
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "reference_paths": [],
    }
    shot = {
        "prompt": "She opens the door and continues speaking.",
        "duration_seconds": 8,
        "dialogue": "I made it.",
        "audio_cues": "Rain remains audible outside.",
        "transition": "continuous",
    }
    target = tmp_path / "turn.mp4"
    interaction_id = video_worker._generate_turn(
        FakeClient(),
        api_key="test-key",
        model="gemini-omni-1.1-flash",
        plan=plan,
        shot=shot,
        target=target,
        previous_interaction_id="v1_prev",
        root=tmp_path,
        continuity_frame=None,
    )

    assert interaction_id == "v1_next"
    assert target.read_bytes() == output
    body = seen["json"]
    assert body["previous_interaction_id"] == "v1_prev"
    assert body["store"] is True
    assert body["generation_config"] == {"video_config": {"task": "extend"}}
    assert "I made it." in body["input"]
    assert "recurring voices acoustically consistent" in body["input"]


def test_video_catalog_detects_modified_file(tmp_path: Path) -> None:
    root = tmp_path
    target = root / "final.mp4"
    target.write_bytes(b"first")
    digest = __import__("hashlib").sha256(b"first").hexdigest()
    manifest = root / ".synapse" / "video-assets.jsonl"
    manifest.parent.mkdir()
    manifest.write_text(
        '{"kind":"generated_video","path":"final.mp4","sha256":"' + digest + '"}\n',
        encoding="utf-8",
    )
    assert video_asset_catalog.audit_video_assets(root)["healthy"] is True
    target.write_bytes(b"changed")
    audit = video_asset_catalog.audit_video_assets(root)
    assert audit["healthy"] is False
    assert audit["modified_paths"] == ["final.mp4"]
