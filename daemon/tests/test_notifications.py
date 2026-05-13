"""Contract #22 — notifications."""

from __future__ import annotations

import pytest

from synapse_daemon.notifications import (
    KNOWN_EVENT_KINDS,
    Notification,
    NotificationLevel,
    assert_known_event_kind,
)


def test_notification_minimal() -> None:
    n = Notification(
        event_kind="process.crashed",
        level=NotificationLevel.ERROR,
        title="wbscrper crashed",
        body="Exit code 1",
    )
    assert n.entity_type is None
    assert n.action_url is None


def test_known_event_kinds_cover_core_events() -> None:
    # Must include every kind referenced in Round 2 contract docs.
    for required in (
        "process.crashed",
        "project.health_unhealthy",
        "tunnel.live",
        "scheduled.fired",
        "manifest.error",
    ):
        assert required in KNOWN_EVENT_KINDS


def test_assert_known_event_kind_passes() -> None:
    assert_known_event_kind("process.crashed")  # no raise


def test_assert_known_event_kind_rejects_unknown() -> None:
    with pytest.raises(ValueError) as exc:
        assert_known_event_kind("definitely.not.a.thing")
    assert "KNOWN_EVENT_KINDS" in str(exc.value)
