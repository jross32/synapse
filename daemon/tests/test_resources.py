"""Contract #19 — resource observability."""

from __future__ import annotations

from synapse_daemon.resources import ResourceCaps, ResourceSnapshot, over_budget


def _snap(cpu: float = 10.0, rss: float = 100.0) -> ResourceSnapshot:
    return ResourceSnapshot(
        entity_type="project", entity_id="wbscrper", pid=1234,
        cpu_percent=cpu, rss_mb=rss,
    )


def test_no_caps_means_never_over_budget() -> None:
    assert over_budget(ResourceCaps(), _snap(cpu=99, rss=9999)) == []


def test_rss_cap_breach() -> None:
    caps = ResourceCaps(max_rss_mb=200)
    assert over_budget(caps, _snap(rss=300)) == ["max_rss_mb"]
    assert over_budget(caps, _snap(rss=150)) == []


def test_cpu_cap_breach() -> None:
    caps = ResourceCaps(max_cpu_percent=50)
    assert over_budget(caps, _snap(cpu=80)) == ["max_cpu_percent"]
    assert over_budget(caps, _snap(cpu=10)) == []


def test_both_caps_breached() -> None:
    caps = ResourceCaps(max_rss_mb=100, max_cpu_percent=20)
    breaches = over_budget(caps, _snap(cpu=99, rss=999))
    assert set(breaches) == {"max_rss_mb", "max_cpu_percent"}
