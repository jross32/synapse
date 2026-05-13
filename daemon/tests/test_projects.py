"""Contracts #1, #2, #10 — project registry CRUD + validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_daemon.errors import SynapseError
from synapse_daemon.models import EntityStatus, ErrorRef
from synapse_daemon.projects import (
    Project,
    ProjectUpdate,
    create,
    get,
    get_or_none,
    list_projects,
    model_dump_for_client,
    set_health,
    set_status,
    soft_delete,
    update,
)
from synapse_daemon.health import HealthState
from synapse_daemon.secrets import EnvVar, SECRET_PLACEHOLDER
from synapse_daemon.storage import Storage


def _storage(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    return s


def _seed(s: Storage, **overrides) -> Project:
    base = {
        "id": "wbscrper",
        "name": "Web Scraper",
        "path": "C:/Users/justi/wbscrper",
        "launch_cmd": "npm start",
    }
    base.update(overrides)
    p = Project(**base)
    with s.transaction() as conn:
        return create(conn, p)


# ── validation ───────────────────────────────────────────────────────────


def test_id_must_be_kebab_case() -> None:
    with pytest.raises(ValueError):
        Project(id="Wbscrper", name="x", path="/", launch_cmd="x")
    with pytest.raises(ValueError):
        Project(id="my_project", name="x", path="/", launch_cmd="x")
    # Single letter is allowed, kebab is allowed.
    Project(id="a", name="x", path="/", launch_cmd="x")
    Project(id="web-scraper", name="x", path="/", launch_cmd="x")


# ── CRUD ─────────────────────────────────────────────────────────────────


def test_create_and_get(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        _seed(s)
        got = get(s.conn, "wbscrper")
        assert got.id == "wbscrper"
        assert got.status == EntityStatus.IDLE
        assert got.current_health == HealthState.UNKNOWN
        assert got.created_at == got.updated_at == got.last_transition_at
    finally:
        s.close()


def test_create_rejects_duplicate(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        _seed(s)
        with pytest.raises(SynapseError) as exc:
            with s.transaction() as conn:
                create(conn, Project(id="wbscrper", name="x", path="/", launch_cmd="x"))
        assert exc.value.envelope.code == "project.conflict"
    finally:
        s.close()


def test_get_or_none_returns_none_for_missing(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        assert get_or_none(s.conn, "missing") is None
    finally:
        s.close()


def test_get_raises_not_found(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        with pytest.raises(SynapseError) as exc:
            get(s.conn, "missing")
        assert exc.value.envelope.code == "project.not_found"
        assert exc.value.status == 404
    finally:
        s.close()


def test_list_projects_excludes_deleted(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        _seed(s)
        with s.transaction() as conn:
            soft_delete(conn, "wbscrper")
        assert list_projects(s.conn) == []
        assert len(list_projects(s.conn, include_deleted=True)) == 1
    finally:
        s.close()


def test_update_partial(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        _seed(s)
        with s.transaction() as conn:
            renamed = update(conn, "wbscrper", ProjectUpdate(name="Web Scraper v2"))
        assert renamed.name == "Web Scraper v2"
        assert renamed.path == "C:/Users/justi/wbscrper"  # unchanged
        # updated_at moves; created_at does not.
        assert renamed.updated_at > renamed.created_at
    finally:
        s.close()


def test_update_empty_raises(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        _seed(s)
        with pytest.raises(SynapseError) as exc:
            with s.transaction() as conn:
                update(conn, "wbscrper", ProjectUpdate())
        assert exc.value.envelope.code == "project.invalid"
    finally:
        s.close()


def test_soft_delete_refuses_while_running(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        _seed(s)
        with s.transaction() as conn:
            set_status(conn, "wbscrper", status=EntityStatus.LAUNCHED)
        with pytest.raises(SynapseError) as exc:
            with s.transaction() as conn:
                soft_delete(conn, "wbscrper")
        assert exc.value.envelope.code == "project.conflict"
    finally:
        s.close()


def test_set_status_advances_last_transition_only_on_change(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        _seed(s)
        first = get(s.conn, "wbscrper")
        with s.transaction() as conn:
            same = set_status(conn, "wbscrper", status=EntityStatus.IDLE)
        # Same status: last_transition_at unchanged.
        assert same.last_transition_at == first.last_transition_at
        with s.transaction() as conn:
            moved = set_status(conn, "wbscrper", status=EntityStatus.LAUNCHED)
        assert moved.last_transition_at > first.last_transition_at
    finally:
        s.close()


def test_set_status_stores_and_clears_error(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        _seed(s)
        with s.transaction() as conn:
            errored = set_status(
                conn, "wbscrper",
                status=EntityStatus.ERROR,
                error=ErrorRef(code="project.spawn_failed", message="No such file"),
            )
        assert errored.last_error is not None
        assert errored.last_error.code == "project.spawn_failed"
        # Returning to a clean state clears the error reference.
        with s.transaction() as conn:
            cleared = set_status(conn, "wbscrper", status=EntityStatus.LAUNCHED)
        assert cleared.last_error is None
    finally:
        s.close()


def test_set_health_records_state_and_time(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        _seed(s)
        with s.transaction() as conn:
            updated = set_health(conn, "wbscrper", state=HealthState.HEALTHY)
        assert updated.current_health == HealthState.HEALTHY
        assert updated.last_health_at is not None
    finally:
        s.close()


# ── client serialisation (Contract #25 redaction) ────────────────────────


def test_model_dump_for_client_redacts_secrets(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        _seed(s, env=[
            EnvVar(key="API_KEY", value="real-secret", secret=True),
            EnvVar(key="LOG_LEVEL", value="info", secret=False),
        ])
        project = get(s.conn, "wbscrper")
        client_view = model_dump_for_client(project)
        env_by_key = {v["key"]: v for v in client_view["env"]}
        assert env_by_key["API_KEY"]["value"] == SECRET_PLACEHOLDER
        assert env_by_key["LOG_LEVEL"]["value"] == "info"
    finally:
        s.close()
