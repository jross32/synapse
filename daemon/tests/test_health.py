"""Contract #17 — health-check protocol."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from synapse_daemon.health import HealthProbe, HealthSnapshot, HealthState, is_terminal


def test_default_probe_is_none() -> None:
    p = HealthProbe()
    assert p.kind == "none"
    assert p.target is None
    assert p.interval_seconds == 15


def test_http_probe() -> None:
    p = HealthProbe(kind="http", target="http://localhost:12345/health", expect_status=200)
    assert p.kind == "http"


def test_interval_bounds() -> None:
    with pytest.raises(ValidationError):
        HealthProbe(interval_seconds=0)
    with pytest.raises(ValidationError):
        HealthProbe(interval_seconds=10_000)


def test_snapshot_defaults() -> None:
    s = HealthSnapshot(project_id="wbscrper")
    assert s.state == HealthState.UNKNOWN
    assert s.consecutive_failures == 0
    assert s.last_probed_at is None


def test_is_terminal() -> None:
    assert is_terminal(HealthState.HEALTHY)
    assert is_terminal(HealthState.UNHEALTHY)
    assert not is_terminal(HealthState.UNKNOWN)
    assert not is_terminal(HealthState.DEGRADED)
