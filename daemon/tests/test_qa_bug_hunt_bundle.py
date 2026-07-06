"""QA & Bug-Hunt Squad bundle installs with correct per-role MCP binding (Plan 3 Phase 1)."""

from __future__ import annotations

from pathlib import Path

from synapse_daemon import agent_squads as squads
from synapse_daemon import ai_bundles
from synapse_daemon import personalities as personalities_module
from synapse_daemon.storage import Storage


def _storage(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    return s


def _bundle() -> ai_bundles.AiBundleManifest:
    return next(b for b in ai_bundles.load_catalog() if b.id == "qa-bug-hunt-squad")


def test_bundle_present_in_catalog() -> None:
    b = _bundle()
    assert len(b.roles) == 9
    assert len(b.personalities) == 12


def test_bundle_installs_roles_with_scoped_mcp(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        ai_bundles.install_bundle(conn, storage.data_dir, _bundle())
    # Browser hunters get only Playwright.
    for rid in ("user-simulator", "edge-case-hunter", "state-corruptor", "ux-critic", "a11y-auditor"):
        assert squads.get_role_template(storage.conn, rid).mcp_server_ids == ["playwright"], rid
    # Coordination roles get no MCP at all (token-lean).
    for rid in ("qa-lead", "triage-steward", "bug-report-synthesist", "token-steward"):
        assert squads.get_role_template(storage.conn, rid).mcp_server_ids == [], rid


def test_bundle_installs_personalities(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        ai_bundles.install_bundle(conn, storage.data_dir, _bundle())
    assert personalities_module.get_personality(storage.conn, "impatient-user").name == "The Impatient User"
    assert personalities_module.get_personality(storage.conn, "mobile-thumb").name == "The Mobile Thumb"


def test_bundle_reinstall_is_idempotent(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        ai_bundles.install_bundle(conn, storage.data_dir, _bundle())
    with storage.transaction() as conn:
        ai_bundles.install_bundle(conn, storage.data_dir, _bundle(), force=True)
    assert squads.get_role_template(storage.conn, "user-simulator").mcp_server_ids == ["playwright"]
