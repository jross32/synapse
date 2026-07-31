from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from synapse_daemon import ai_bundles, skill_packs
from synapse_daemon.app import build_app
from synapse_daemon.errors import SynapseError
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


def _pipeline_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "templates"
        / "skills"
        / "super-internet-digger"
        / "scripts"
        / "digger_pipeline.py"
    )
    spec = importlib.util.spec_from_file_location("digger_pipeline_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    original = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = original
    return module


def test_skill_catalog_validates_package_and_benchmark() -> None:
    catalog = skill_packs.load_catalog()
    assert [item.manifest.id for item in catalog] == ["super-internet-digger"]
    item = catalog[0]
    assert item.package_sha256
    assert any(resource.path == "SKILL.md" for resource in item.resources)
    assert any(resource.path == "references/benchmark-spec.json" for resource in item.resources)
    spec = skill_packs.load_benchmark_spec(
        skill_packs.bundled_skill_packs_dir() / item.manifest.id,
        item.manifest,
    )
    assert spec.id == "super-internet-digger-v2"
    assert spec.default_repeat_count == 5
    assert len(spec.scenarios) == 7
    assert spec.metadata["target_speed_multiplier"] == 4.0


def test_bundle_install_versions_skill_and_seeds_benchmark(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    bundle = ai_bundles.bundle_by_id("super-internet-digger")
    with storage.transaction() as conn:
        installed_bundle = ai_bundles.install_bundle(conn, storage.data_dir, bundle)

    installed = skill_packs.get_installed(storage.data_dir, "super-internet-digger")
    assert installed.manifest.version == "2.0.0"
    assert Path(installed.path, "SKILL.md").is_file()
    assert installed.benchmark_spec_id == "super-internet-digger-v2"
    assert installed_bundle.bundle_id == bundle.id
    owned = ai_bundles.list_owned_assets(storage.conn, bundle.id)
    assert any(asset.kind == ai_bundles.AiBundleAssetKind.SKILL_PACK for asset in owned)
    assert storage.conn.execute(
        "SELECT COUNT(*) AS count FROM benchmark_specs WHERE id = ?",
        ("super-internet-digger-v2",),
    ).fetchone()["count"] == 1

    with storage.transaction() as conn:
        result = ai_bundles.uninstall_bundle(conn, storage.data_dir, bundle.id)
    assert "skill_pack:super-internet-digger" in result["removed_assets"]
    assert not (storage.data_dir / "skill-packs" / "super-internet-digger").exists()
    assert storage.conn.execute(
        "SELECT COUNT(*) AS count FROM benchmark_specs WHERE id = ?",
        ("super-internet-digger-v2",),
    ).fetchone()["count"] == 1


def test_skill_routes_and_mcp_expose_installed_instructions(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    app = build_app(storage, EventBus())
    token = app.state.auth.local_token
    headers = {"X-Synapse-Token": token}

    with TestClient(app, headers=headers) as client:
        before = client.get("/api/v1/ai-bundles/skills")
        assert before.status_code == 200
        assert before.json()["installed_ids"] == []

        install = client.post("/api/v1/ai-bundles/install/super-internet-digger")
        assert install.status_code == 200, install.text
        after = client.get("/api/v1/ai-bundles/skills")
        assert after.json()["installed_ids"] == ["super-internet-digger"]
        detail = client.get("/api/v1/ai-bundles/skills/super-internet-digger")
        assert detail.status_code == 200
        assert "Fast Research Loop" in detail.json()["instructions_md"]
        context = client.get("/api/v1/ai/context").json()
        advertised_paths = " ".join(item["path"] for item in context["endpoints_for_ai"])
        assert "/api/v1/ai-bundles/skills" in advertised_paths

        rpc = client.post(
            f"/mcp/{token}",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        names = {item["name"] for item in rpc.json()["result"]["tools"]}
        assert {"synapse_list_skill_packs", "synapse_get_skill_pack"} <= names
        read = client.post(
            f"/mcp/{token}",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "synapse_get_skill_pack",
                    "arguments": {"skill_id": "super-internet-digger"},
                },
            },
        )
        assert read.json()["result"]["isError"] is False
        assert "Super Internet Digger" in read.json()["result"]["content"][0]["text"]


def test_skill_resource_path_cannot_escape_package(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    skill_packs.install(storage.data_dir, "super-internet-digger")
    with pytest.raises(SynapseError):
        skill_packs.read_resource(storage.data_dir, "super-internet-digger", "../manifest.json")


def test_skill_versions_are_immutable(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    installed = skill_packs.install(storage.data_dir, "super-internet-digger")
    Path(installed.path, "SKILL.md").write_text("changed without version bump", encoding="utf-8")
    with pytest.raises(SynapseError, match="immutable"):
        skill_packs.install(storage.data_dir, "super-internet-digger")
    with pytest.raises(SynapseError, match="integrity"):
        skill_packs.read_instructions(storage.data_dir, "super-internet-digger")


def test_pipeline_plans_parallel_direct_tools_with_optional_warden() -> None:
    pipeline = _pipeline_module()
    plan = pipeline.build_plan(
        "Example",
        "both",
        {"github", "web-scraper", "web", "warden"},
        None,
    )
    assert {lane["parallel_group"] for lane in plan["lanes"]} == {1}
    assert plan["tool_policy"]["direct_tools_remain_available"] is True
    assert plan["tool_policy"]["warden_role"] == "optional-router"
    assert plan["permission_gates"] == ["discovery", "acquisition", "execution"]


def test_pipeline_blocks_leaks_and_prefers_verified_official_candidate() -> None:
    pipeline = _pipeline_module()
    recent = (date.today() - timedelta(days=20)).isoformat()
    payload = {
        "candidates": [
            {
                "id": "bad",
                "name": "Leaked mirror",
                "artifact_kind": "source-code",
                "source_type": "leaked-source",
                "access_mode": "public-web",
                "upstream_url": "https://mirror.invalid/drop",
                "release_date": recent,
                "license": "Unknown",
                "provenance_confidence": "low",
                "acquisition_allowed": False,
                "acquisition_reason": "Unauthorized provenance",
                "confirmation_required": True,
                "user_confirmed": False,
                "playable_potential": "likely",
                "evidence_ids": ["e1"],
            },
            {
                "id": "official",
                "name": "Official release",
                "artifact_kind": "source-code",
                "source_type": "official-public",
                "access_mode": "public-git",
                "upstream_url": "https://github.com/example/project",
                "version_label": "v2.0.0",
                "release_date": recent,
                "license": "MIT",
                "provenance_confidence": "high",
                "acquisition_allowed": True,
                "acquisition_reason": "Official MIT repository",
                "confirmation_required": False,
                "user_confirmed": False,
                "playable_potential": "ready",
                "reproduction_steps": ["git clone --branch v2.0.0 ..."],
                "evidence_ids": ["e2", "e3"],
            },
        ]
    }
    ranked = pipeline.rank_candidates(payload)
    assert ranked["selected"]["source-code"]["id"] == "official"
    leaked = next(item for item in ranked["candidates"] if item["id"] == "bad")
    assert leaked["ranking"]["eligible"] is False
    assert "unauthorized-provenance" in leaked["ranking"]["blockers"]


def test_pipeline_single_pass_inspector_detects_polyglot_project(tmp_path: Path) -> None:
    pipeline = _pipeline_module()
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite"}, "dependencies": {"vite": "1.0.0"}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    result = pipeline.inspect_project(tmp_path)
    assert result["polyglot"] is True
    assert {item["type"] for item in result["detections"]} >= {"node-web", "python-app"}
    assert result["execution_performed"] is False
    node = next(item for item in result["detections"] if item["type"] == "node-web")
    assert node["install_commands"] == ["npm ci"]


def test_pipeline_only_allows_four_x_claim_when_quality_and_safety_hold() -> None:
    pipeline = _pipeline_module()
    baseline = {
        "name": "baseline",
        "attempts": [
            {"quality_score_100": 80, "elapsed_seconds": 400, "total_tokens": 8000, "tool_calls": 20, "critical_errors": 0}
        ],
    }
    challenger = {
        "name": "challenger",
        "attempts": [
            {"quality_score_100": 90, "elapsed_seconds": 80, "total_tokens": 1500, "tool_calls": 4, "critical_errors": 0}
        ],
    }
    result = pipeline.compare_metrics(baseline, challenger)
    assert result["claims"]["four_x_faster"] is True
    assert result["claims"]["four_x_token_efficient"] is True

    challenger["attempts"][0]["critical_errors"] = 1
    unsafe = pipeline.compare_metrics(baseline, challenger)
    assert unsafe["claims"]["four_x_faster"] is False
    assert unsafe["eligible_winner"] is False
