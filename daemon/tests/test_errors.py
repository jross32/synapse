"""Contract #4 — error envelope tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from synapse_daemon.errors import ErrorEnvelope, SynapseError, conflict, invalid, not_found


def test_error_envelope_minimal() -> None:
    e = ErrorEnvelope(code="project.not_found", message="Project x missing")
    assert e.code == "project.not_found"
    assert e.message == "Project x missing"
    assert e.details is None
    assert e.retryable is False


def test_error_envelope_full() -> None:
    e = ErrorEnvelope(
        code="ws.replay_window_exceeded",
        message="Lost too many events to replay",
        details={"since": 12, "buffer_min_id": 200},
        retryable=True,
    )
    assert e.retryable is True
    assert e.details is not None
    assert e.details["since"] == 12


def test_error_envelope_requires_code_and_message() -> None:
    with pytest.raises(ValidationError):
        ErrorEnvelope(message="missing code")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ErrorEnvelope(code="x")  # type: ignore[call-arg]


def test_synapse_error_carries_envelope() -> None:
    err = SynapseError("project.not_found", "Project foo missing", status=404)
    assert err.envelope.code == "project.not_found"
    assert err.status == 404
    assert str(err) == "Project foo missing"


def test_helper_constructors_use_correct_codes() -> None:
    assert not_found("project", "x").envelope.code == "project.not_found"
    assert not_found("project", "x").status == 404
    assert conflict("project", "duplicate name").envelope.code == "project.conflict"
    assert conflict("project", "x").status == 409
    assert invalid("project", "bad path").envelope.code == "project.invalid"
    assert invalid("project", "x").status == 422


def test_helper_attaches_details() -> None:
    err = conflict("project", "duplicate name", existing_id="abc", attempted_name="abc")
    assert err.envelope.details == {"existing_id": "abc", "attempted_name": "abc"}
