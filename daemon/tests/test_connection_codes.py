"""Connection status code catalog + classification (ADR-0028, PLAN 5 Phase 1)."""

from __future__ import annotations

from synapse_daemon.connection_codes import (
    ConnectionLevel,
    catalog,
    classify,
    get,
)


def test_classify_green_when_all_up() -> None:
    c = classify(mcp_all_connected=True, has_project=True)
    assert c.code == "ok"
    assert c.level is ConnectionLevel.GREEN
    assert c.remedy == ""  # nothing to do


def test_classify_yellow_when_mcp_offline() -> None:
    c = classify(mcp_all_connected=False, has_project=True)
    assert c.code == "degraded.mcp_unavailable"
    assert c.level is ConnectionLevel.YELLOW
    assert c.remedy  # a degraded code always tells the operator what to do


def test_classify_yellow_when_no_project() -> None:
    c = classify(mcp_all_connected=True, has_project=False)
    assert c.code == "degraded.no_project"
    assert c.level is ConnectionLevel.YELLOW


def test_mcp_offline_takes_precedence_over_no_project() -> None:
    # Most-severe-first: an offline tool is reported before the missing-project note.
    c = classify(mcp_all_connected=False, has_project=False)
    assert c.code == "degraded.mcp_unavailable"


def test_get_unknown_code_degrades_to_failed_internal() -> None:
    c = get("nope.not.a.real.code")
    assert c.code == "failed.internal"
    assert c.level is ConnectionLevel.RED


def test_catalog_is_complete_and_well_formed() -> None:
    codes = catalog()
    keys = {c.code for c in codes}
    assert {"ok", "degraded.mcp_unavailable", "degraded.no_project", "failed.internal"} <= keys
    # Every non-green code must carry a remedy so failures are self-diagnosing.
    for c in codes:
        assert c.title and c.explanation
        if c.level is not ConnectionLevel.GREEN:
            assert c.remedy, f"{c.code} (non-green) must have a remedy"
