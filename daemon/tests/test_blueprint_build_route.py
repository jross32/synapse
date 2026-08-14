"""The build endpoint after the ladder: paid runtimes first, Ollama only when needed.

The endpoint used to refuse outright unless Ollama was installed and running. That was
correct when every build was local. It is wrong now: a build routed to Claude has no use for
Ollama, and making a paid runtime depend on a free one being installed would block the
common case on the fallback's absence.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from synapse_daemon import coder_runtimes as cr
from synapse_daemon import ollama_client
from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _client(tmp_path) -> TestClient:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


@pytest.fixture(autouse=True)
def _no_cooldowns():
    cr.clear_exhausted()
    yield
    cr.clear_exhausted()


def test_a_paid_build_does_not_require_ollama(tmp_path, monkeypatch):
    """The common case must not be blocked by the fallback tier being absent."""
    monkeypatch.setattr(ollama_client, "is_installed", lambda: False)

    built: dict = {}

    async def fake_build(bp, **kwargs):
        built.update(kwargs)
        from synapse_daemon.scaffold.runner import BuildResult
        return BuildResult(blueprint_id=bp.id, workspace=str(kwargs["workspace"]))

    monkeypatch.setattr("synapse_daemon.scaffold.runner.build_blueprint", fake_build)

    response = _client(tmp_path).post(
        "/api/v1/blueprints/webapp-auth-crud/build",
        json={"workspace": str(tmp_path / "ws"), "runtimes": ["claude"]})

    assert response.status_code == 200, response.text
    assert built["ladder"] == (cr.CoderRuntime.CLAUDE,)


def test_a_build_that_would_reach_local_still_checks_ollama(tmp_path, monkeypatch):
    """Falling to a tier that cannot run is a failure worth reporting up front."""
    monkeypatch.setattr(ollama_client, "is_installed", lambda: False)
    monkeypatch.setattr(cr, "available", lambda runtime: False)

    response = _client(tmp_path).post(
        "/api/v1/blueprints/webapp-auth-crud/build",
        json={"workspace": str(tmp_path / "ws"), "runtimes": ["local"]})

    assert response.status_code >= 400
    assert "ollama" in response.text.lower()


def test_an_unknown_runtime_is_refused_by_name(tmp_path):
    response = _client(tmp_path).post(
        "/api/v1/blueprints/webapp-auth-crud/build",
        json={"workspace": str(tmp_path / "ws"), "runtimes": ["gpt-9"]})

    assert response.status_code >= 400
    assert "gpt-9" in response.text


def test_overnight_attempts_are_passed_through_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(ollama_client, "is_installed", lambda: True)

    built: dict = {}

    async def fake_build(bp, **kwargs):
        built.update(kwargs)
        from synapse_daemon.scaffold.runner import BuildResult
        return BuildResult(blueprint_id=bp.id, workspace=str(kwargs["workspace"]))

    monkeypatch.setattr("synapse_daemon.scaffold.runner.build_blueprint", fake_build)

    client = _client(tmp_path)
    client.post("/api/v1/blueprints/webapp-auth-crud/build",
                json={"workspace": str(tmp_path / "ws"), "runtimes": ["claude"],
                      "max_attempts": 6})
    assert built["max_attempts"] == 6

    # An unbounded retry count would be a way to spend a whole night, or a whole budget,
    # by typo.
    client.post("/api/v1/blueprints/webapp-auth-crud/build",
                json={"workspace": str(tmp_path / "ws"), "runtimes": ["claude"],
                      "max_attempts": 9999})
    assert built["max_attempts"] == 20
