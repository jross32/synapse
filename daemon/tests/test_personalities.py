"""Tests for AI personalities — a worker = role + personality (ADR-0018 MW3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon import personalities as pers
from synapse_daemon.ai_context_memory import write_role_prompt
from synapse_daemon.app import build_app
from synapse_daemon.errors import SynapseError
from synapse_daemon.personalities import PersonalityCreate, PersonalityUpdate
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

_BUILTINS = {"pragmatist", "perfectionist", "skeptic", "visionary", "mediator"}


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


def _harness(tmp_path: Path) -> TestClient:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        create(conn, Project(id="demo-project", name="Demo", path=str(tmp_path), launch_cmd="echo hi"))
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


# ── seeding + module CRUD ────────────────────────────────────────────────────


def test_defaults_seeded(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        pers.seed_default_personalities(conn)
    all_p = pers.list_personalities(storage.conn)
    ids = {p.id for p in all_p}
    assert _BUILTINS <= ids
    assert all(p.builtin for p in all_p if p.id in _BUILTINS)
    # seeding twice is idempotent
    with storage.transaction() as conn:
        pers.seed_default_personalities(conn)
    assert len(pers.list_personalities(storage.conn)) == len(all_p)


def test_crud_roundtrip(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        created = pers.create_personality(
            conn, PersonalityCreate(id="zen", name="The Zen", traits=["calm"], prompt_preamble_md="Stay calm.")
        )
    assert created.id == "zen" and created.builtin is False
    with storage.transaction() as conn:
        updated = pers.update_personality(conn, "zen", PersonalityUpdate(blurb="calm dev", traits=["calm", "focused"]))
    assert updated.blurb == "calm dev"
    assert updated.traits == ["calm", "focused"]
    with storage.transaction() as conn:
        pers.delete_personality(conn, "zen")
    assert all(p.id != "zen" for p in pers.list_personalities(storage.conn))


def test_duplicate_id_conflicts(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        pers.create_personality(conn, PersonalityCreate(id="dup", name="A"))
    with pytest.raises(SynapseError):
        with storage.transaction() as conn:
            pers.create_personality(conn, PersonalityCreate(id="dup", name="B"))


# ── HTTP endpoints ───────────────────────────────────────────────────────────


def test_endpoints_seed_create_and_protect_builtins(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    listed = client.get("/api/v1/personalities")
    assert listed.status_code == 200
    assert _BUILTINS <= {p["id"] for p in listed.json()["personalities"]}

    created = client.post(
        "/api/v1/personalities",
        json={"id": "tinker", "name": "The Tinkerer", "prompt_preamble_md": "Experiment first."},
    )
    assert created.status_code == 201, created.text
    assert created.json()["id"] == "tinker"

    # built-ins are protected from deletion (they'd just re-seed anyway)
    assert client.delete("/api/v1/personalities/skeptic").status_code == 409
    # custom ones delete cleanly
    assert client.delete("/api/v1/personalities/tinker").status_code == 204


def test_work_item_carries_personality(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    squad = client.post(
        "/api/v1/agent-squads",
        json={"project_id": "demo-project", "name": "Crew", "goal_md": "Ship it.", "lead_role_id": "planner"},
    ).json()
    item = client.post(
        f"/api/v1/agent-squads/{squad['id']}/work-items",
        json={"title": "Design the nav", "assigned_role_id": "designer", "personality_id": "skeptic"},
    )
    assert item.status_code == 201, item.text
    assert item.json()["personality_id"] == "skeptic"


# ── prompt layering ──────────────────────────────────────────────────────────


def _prompt(tmp_path: Path, **extra) -> str:
    path = write_role_prompt(
        data_dir=tmp_path,
        project_id="proj",
        project_name="Proj",
        squad_name="Squad",
        squad_goal_md="goal",
        work_item_title="Do a thing",
        instructions_md="instructions",
        role_name="Designer",
        role_description="Owns UX",
        prompt_preamble_md="design well",
        context_mode="standard",
        handoff_summary_md=None,
        handoff_blockers_md=None,
        files_touched=[],
        **extra,
    )
    return path.read_text(encoding="utf-8")


def test_prompt_includes_personality_section(tmp_path: Path) -> None:
    text = _prompt(tmp_path, personality_name="The Skeptic", personality_preamble_md="Question assumptions.")
    assert "## Personality" in text
    assert "The Skeptic" in text
    assert "Question assumptions." in text


def test_prompt_without_personality_is_graceful(tmp_path: Path) -> None:
    text = _prompt(tmp_path)
    assert "## Personality" in text
    assert "No specific personality" in text
