"""Contract #2 (live status fields), #8 (canonical schema), #10 (naming)."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from synapse_daemon.api_versions import API_PREFIX, API_VERSION, event_name
from synapse_daemon.models import (
    AuditSource,
    BaseEntity,
    EntityStatus,
    ErrorRef,
    HealthResponse,
    StateTransition,
    model_registry,
)


def test_base_entity_required_fields() -> None:
    e = BaseEntity(id="wbscrper", name="Web Scraper")
    # Contract #2 universal fields:
    assert e.status == EntityStatus.IDLE
    assert e.last_error is None
    assert e.created_at == e.updated_at == e.last_transition_at


def test_entity_status_values_match_contract() -> None:
    # Contract #2 state machine.
    expected = {"idle", "launching", "launched", "stopping", "stopped", "error"}
    actual = {s.value for s in EntityStatus}
    assert actual == expected


def test_audit_source_values() -> None:
    # Contract #11.
    assert {s.value for s in AuditSource} == {"desktop", "mobile", "tray", "cli", "auto"}


def test_state_transition_minimal() -> None:
    t = StateTransition(
        entity_id="wbscrper",
        from_status=EntityStatus.IDLE,
        to_status=EntityStatus.LAUNCHING,
    )
    assert t.source == AuditSource.AUTO
    assert t.note is None


def test_error_ref_records_a_compact_failure() -> None:
    ref = ErrorRef(code="tunnel.cloudflared_missing", message="cloudflared not on PATH")
    assert ref.occurred_at is not None


def test_id_kebab_case_recommended() -> None:
    # Contract #10 says IDs are kebab-case. The model does not enforce this
    # at the Pydantic layer (callers can pass anything); the validator lives
    # in the project-registry CRUD layer (Milestone D). This test documents
    # the intended pattern.
    pattern = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    for example in ("wbscrper", "ollama-chat", "cloudtap", "web-scraper-2"):
        assert pattern.match(example), example


def test_api_version_constants() -> None:
    # Contract #7.
    assert API_VERSION == "v1"
    assert API_PREFIX == "/api/v1"
    assert event_name("project", "launched") == "v1.project.launched"


def test_health_response_default_contracts_list() -> None:
    h = HealthResponse(ok=True, version="0.1.2", started_at=__import__("datetime").datetime.now())
    # Contracts #1–#28 honoured by the daemon as of v0.1.2 (Round 2 scaffolded).
    assert h.contracts == list(range(1, 29))


def test_model_registry_exposes_all_shared_models() -> None:
    # Contract #8 — gen-types.ps1 reads this list.
    reg = model_registry()
    for key in (
        # Round 1
        "ErrorEnvelope",
        "EntityStatus",
        "AuditSource",
        "ErrorRef",
        "BaseEntity",
        "StateTransition",
        "HealthResponse",
        # Round 2
        "HealthState",
        "HealthProbe",
        "HealthSnapshot",
        "RestartPolicy",
        "ResourceSnapshot",
        "ResourceCaps",
        "Notification",
        "NotificationLevel",
        "EnvVar",
        "SnapshotPayload",
        "RestoreReport",
    ):
        assert key in reg, f"model_registry missing {key}"


def test_base_entity_validate_assignment() -> None:
    # Defensive: assignment is validated, so accidentally setting status to
    # a non-enum string fails loudly instead of silently corrupting state.
    e = BaseEntity(id="x", name="X")
    with pytest.raises(ValidationError):
        e.status = "running"  # type: ignore[assignment]
