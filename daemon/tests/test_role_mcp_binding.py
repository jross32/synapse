"""Per-role MCP server binding (Plan 3 Phase 1, ADR-0025).

A role scopes which MCP servers its workers receive:
``mcp_server_ids`` None -> all enabled (backward-compatible); [] -> none
(token-lean); [ids] -> only those (e.g. a browser role gets just Playwright).
"""

from __future__ import annotations

import json
from pathlib import Path

from synapse_daemon import agent_squads as squads
from synapse_daemon import mcp_servers as mcp
from synapse_daemon.routes_agent_squads import _write_mcp_config
from synapse_daemon.storage import Storage


def _server(sid: str, *, enabled: bool = True) -> mcp.McpServer:
    return mcp.McpServer(
        id=sid,
        name=sid.title(),
        transport=mcp.McpTransport.STDIO,
        command="npx",
        args=["-y", f"@{sid}/mcp"],
        enabled=enabled,
        created_at="2026-07-05T00:00:00Z",
        updated_at="2026-07-05T00:00:00Z",
    )


# -- build_mcp_config filtering -----------------------------------------------


def test_build_mcp_config_none_includes_all_enabled() -> None:
    out = mcp.build_mcp_config([_server("playwright"), _server("filesystem")])["mcpServers"]
    assert set(out) == {"playwright", "filesystem"}


def test_build_mcp_config_allow_ids_filters_to_subset() -> None:
    out = mcp.build_mcp_config([_server("playwright"), _server("filesystem")], ["playwright"])["mcpServers"]
    assert set(out) == {"playwright"}


def test_build_mcp_config_empty_allow_ids_yields_none() -> None:
    out = mcp.build_mcp_config([_server("playwright"), _server("filesystem")], [])["mcpServers"]
    assert out == {}


def test_build_mcp_config_skips_disabled_even_if_allowed() -> None:
    out = mcp.build_mcp_config([_server("playwright", enabled=False)], ["playwright"])["mcpServers"]
    assert out == {}


# -- role persistence roundtrip -----------------------------------------------


def _storage(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    return s


def _role(sid: str, mcp_ids: list[str] | None) -> squads.AgentRoleTemplateCreate:
    return squads.AgentRoleTemplateCreate(
        id=sid, name=sid, role_tier=squads.AgentRoleTier.WORKER, mcp_server_ids=mcp_ids
    )


def test_role_mcp_ids_roundtrip(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        squads.create_role_template(conn, _role("r-inherit", None))
        squads.create_role_template(conn, _role("r-none", []))
        squads.create_role_template(conn, _role("r-browser", ["playwright"]))
    assert squads.get_role_template(storage.conn, "r-inherit").mcp_server_ids is None
    assert squads.get_role_template(storage.conn, "r-none").mcp_server_ids == []
    assert squads.get_role_template(storage.conn, "r-browser").mcp_server_ids == ["playwright"]


def test_seeded_roles_inherit_all(tmp_path: Path) -> None:
    # Seeded roles predate the column -> NULL -> None (inherit all): backward-compatible.
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        squads.seed_default_role_templates(conn)
    assert squads.get_role_template(storage.conn, "tester").mcp_server_ids is None


def test_update_role_sets_mcp_ids(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        squads.create_role_template(conn, _role("r-x", None))
        squads.update_role_template(
            conn, "r-x", squads.AgentRoleTemplateUpdate(mcp_server_ids=["playwright"])
        )
    assert squads.get_role_template(storage.conn, "r-x").mcp_server_ids == ["playwright"]


# -- _write_mcp_config scoped by role -----------------------------------------


def test_write_mcp_config_scoped_by_role(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        for sid in ("playwright", "filesystem"):
            mcp.install_server(
                conn,
                mcp.McpServerInstallRequest(
                    id=sid, name=sid.title(), transport=mcp.McpTransport.STDIO,
                    command="npx", args=["-y", f"@{sid}/mcp"],
                ),
                mcp.McpCatalog(servers=[]),
            )
        browser_role = squads.create_role_template(conn, _role("browser-role", ["playwright"]))
        none_role = squads.create_role_template(conn, _role("no-mcp-role", []))
        all_role = squads.create_role_template(conn, _role("all-role", None))

    # Browser role -> only playwright.
    p = _write_mcp_config(storage, browser_role)
    assert p is not None
    assert set(json.loads(p.read_text())["mcpServers"]) == {"playwright"}

    # No-MCP role -> no config at all (launches without --mcp-config).
    assert _write_mcp_config(storage, none_role) is None

    # Inherit-all role -> both servers; distinct filename (no clobber).
    p_all = _write_mcp_config(storage, all_role)
    assert p_all is not None
    assert set(json.loads(p_all.read_text())["mcpServers"]) == {"playwright", "filesystem"}
    assert p.name != p_all.name
