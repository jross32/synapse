"""Tests for AI-facing playbooks (procedures for driving something outside this codebase).

Own scratch Storage per test, nothing bound to a port and nothing touching the real daemon --
same isolation pattern as the rest of the connector suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_daemon import playbooks
from synapse_daemon.errors import SynapseError
from synapse_daemon.storage import Storage


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


def test_upsert_playbook_creates_then_updates_content(tmp_path):
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        created = playbooks.upsert_playbook(
            conn, playbook_id="demo", title="Demo", summary="v1", steps=["one"]
        )
    assert created.status == playbooks.PlaybookStatus.HEALTHY
    assert created.steps == ["one"]

    with storage.transaction() as conn:
        updated = playbooks.upsert_playbook(
            conn, playbook_id="demo", title="Demo", summary="v2", steps=["one", "two"]
        )
    assert updated.summary == "v2"
    assert updated.steps == ["one", "two"]
    assert updated.created_at == created.created_at  # original row, not a new insert


def test_record_verification_updates_status_without_touching_steps(tmp_path):
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        playbooks.upsert_playbook(conn, playbook_id="demo", title="Demo", summary="", steps=["a", "b"])

    with storage.transaction() as conn:
        result = playbooks.record_verification(
            conn, "demo",
            status=playbooks.PlaybookStatus.NEEDS_ATTENTION,
            note="step 2 button renamed",
            verified_by="test-suite",
        )
    assert result.status == playbooks.PlaybookStatus.NEEDS_ATTENTION
    assert result.status_note == "step 2 button renamed"
    assert result.verified_by == "test-suite"
    assert result.steps == ["a", "b"]  # untouched
    assert result.last_verified_at is not None


def test_reseeding_a_playbook_does_not_reset_a_reported_status(tmp_path):
    """The property the docstring promises: re-running bootstrap on every daemon startup
    must not silently erase "an AI already reported this is broken" back to healthy."""
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        playbooks.upsert_playbook(conn, playbook_id="demo", title="Demo", summary="", steps=["a"])
    with storage.transaction() as conn:
        playbooks.record_verification(
            conn, "demo", status=playbooks.PlaybookStatus.BROKEN, note="UI completely changed"
        )

    # Simulate a daemon restart re-running the bootstrap seed with (possibly refreshed) content.
    with storage.transaction() as conn:
        reseeded = playbooks.upsert_playbook(
            conn, playbook_id="demo", title="Demo", summary="refreshed", steps=["a", "b"]
        )
    assert reseeded.status == playbooks.PlaybookStatus.BROKEN
    assert reseeded.status_note == "UI completely changed"
    assert reseeded.steps == ["a", "b"]  # content itself does still refresh


def test_get_unknown_playbook_404s(tmp_path):
    storage = _storage(tmp_path)
    with pytest.raises(SynapseError) as exc_info:
        playbooks.get_playbook(storage.conn, "does-not-exist")
    assert exc_info.value.envelope.code == "playbook.not_found"


def test_list_playbooks_reports_step_count_not_full_steps(tmp_path):
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        playbooks.upsert_playbook(conn, playbook_id="a", title="A", summary="", steps=["1", "2", "3"])
        playbooks.upsert_playbook(conn, playbook_id="b", title="B", summary="", steps=["1"])

    summaries = {s.id: s for s in playbooks.list_playbooks(storage.conn)}
    assert summaries["a"].step_count == 3
    assert summaries["b"].step_count == 1
    assert not hasattr(summaries["a"], "steps")


def test_bootstrap_chatgpt_connector_playbook_seeds_real_steps(tmp_path):
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        seeded = playbooks.ensure_bootstrap_chatgpt_connector_playbook(conn)

    assert seeded.id == playbooks.CHATGPT_CONNECTOR_PLAYBOOK_ID
    assert len(seeded.steps) >= 5
    joined = " ".join(seeded.steps).lower()
    # The two mistakes that actually broke this the first time -- if either is missing
    # from the recorded steps, the playbook has stopped encoding the lesson it exists for.
    assert "try in chat" in joined
    assert "work" in joined and "chat" in joined
