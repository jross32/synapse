"""Warden's optional, version-pinned MCP marketplace integration."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon import mcp_servers as mcp
from synapse_daemon import warden_marketplace as warden
from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> tuple[Storage, TestClient]:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return storage, client


def _fake_release(
    data_dir: Path,
    *,
    version: str = warden.WARDEN_PINNED_VERSION,
    commit: str = warden.WARDEN_PINNED_COMMIT,
    verified_at: str = "2026-07-31T12:00:00+00:00",
) -> warden.WardenRelease:
    release_dir = warden.warden_root(data_dir) / "releases" / warden.release_slug(version, commit)
    python_command = release_dir / ".venv" / "Scripts" / "python.exe"
    python_command.parent.mkdir(parents=True, exist_ok=True)
    python_command.write_bytes(b"fake-python")
    release = warden.WardenRelease(
        version=version,
        commit=commit,
        source_url=warden.WARDEN_SOURCE_URL,
        release_dir=str(release_dir),
        python_command=str(python_command),
        verified_at=verified_at,
    )
    (release_dir / warden.WARDEN_RELEASE_MANIFEST).write_text(
        release.model_dump_json(indent=2), encoding="utf-8"
    )
    return release


def _install_direct(
    storage: Storage,
    *,
    server_id: str,
    command: str | None = "npx",
    transport: mcp.McpTransport = mcp.McpTransport.STDIO,
    url: str | None = None,
    env: dict[str, str] | None = None,
) -> None:
    with storage.transaction() as conn:
        mcp.install_server(
            conn,
            mcp.McpServerInstallRequest(
                id=server_id,
                name=server_id.title(),
                transport=transport,
                command=command,
                args=["-y", f"server-{server_id}"] if command else [],
                url=url,
                env=env or {},
            ),
            mcp.McpCatalog(servers=[]),
        )


def test_catalog_exposes_optional_warden_without_replacing_direct_servers(tmp_path: Path) -> None:
    _storage, client = _harness(tmp_path)
    catalog = {item["id"]: item for item in client.get("/api/v1/mcp-servers/registry").json()["servers"]}

    assert catalog["warden"]["installed"] is False
    assert catalog["warden"]["transport"] == "stdio"
    assert "optional" in catalog["warden"]["tags"]
    assert "memory" in catalog
    assert "web-scraper" in catalog


def test_marketplace_install_activates_only_a_verified_pinned_release(
    tmp_path: Path, monkeypatch
) -> None:
    storage, client = _harness(tmp_path)
    release = _fake_release(storage.data_dir)
    monkeypatch.setattr(warden, "install_pinned_warden", lambda _data_dir: release)

    response = client.post("/api/v1/mcp-servers/install", json={"catalog_id": "warden"})

    assert response.status_code == 201, response.text
    stored = mcp.get_server(storage.conn, warden.WARDEN_SERVER_ID)
    assert stored.command == release.python_command
    assert stored.args == ["-m", "warden", "serve"]
    assert stored.enabled is True
    assert stored.env["WARDEN_CONFIG"] == str(warden.warden_config_path(storage.data_dir))
    status = client.get("/api/v1/mcp-servers/warden/status").json()
    assert status["installed"] is True
    assert status["verified"] is True
    assert status["active_commit"] == warden.WARDEN_PINNED_COMMIT


def test_invalid_release_manifest_is_rejected_and_installed_server_can_be_repaired(tmp_path: Path) -> None:
    storage, client = _harness(tmp_path)
    release = _fake_release(storage.data_dir, commit="not-a-git-commit")
    with storage.transaction() as conn:
        mcp.install_server(
            conn,
            warden.install_request_for(storage.data_dir, release),
            mcp.McpCatalog(servers=[]),
        )

    assert warden.load_release(Path(release.release_dir)) is None
    status = client.get("/api/v1/mcp-servers/warden/status").json()
    assert status["installed"] is True
    assert status["verified"] is False
    assert status["update_available"] is True


def test_registry_sync_indexes_stdio_but_keeps_http_direct_and_secrets_out_of_json(
    tmp_path: Path,
) -> None:
    storage, _client = _harness(tmp_path)
    _install_direct(storage, server_id="github", env={"GITHUB_TOKEN": "secret"})
    _install_direct(
        storage,
        server_id="scraper",
        command=None,
        transport=mcp.McpTransport.HTTP,
        url="http://127.0.0.1:12000/mcp",
    )
    _install_direct(storage, server_id="disabled")
    with storage.transaction() as conn:
        mcp.update_server(conn, "disabled", mcp.McpServerUpdate(enabled=False))
        release = _fake_release(storage.data_dir)
        mcp.install_server(
            conn,
            warden.install_request_for(storage.data_dir, release),
            mcp.McpCatalog(servers=[]),
        )
        result = warden.sync_registry(conn, storage.data_dir)

    assert result.indexed_stdio_servers == ["github"]
    assert result.skipped_http_servers == ["scraper"]
    assert result.skipped_disabled_servers == ["disabled"]
    config = json.loads(warden.warden_config_path(storage.data_dir).read_text(encoding="utf-8"))
    assert set(config["mcp_servers"]) == {"github"}
    assert "env" not in config["mcp_servers"]["github"]
    stored_warden = mcp.get_server(storage.conn, warden.WARDEN_SERVER_ID)
    assert stored_warden.env["GITHUB_TOKEN"] == "secret"
    direct = mcp.build_mcp_config(mcp.list_servers(storage.conn))["mcpServers"]
    assert set(direct) == {"github", "scraper", "warden"}


def test_registry_sync_skips_server_with_conflicting_global_credential_name(tmp_path: Path) -> None:
    storage, _client = _harness(tmp_path)
    _install_direct(storage, server_id="alpha", env={"TOKEN": "one"})
    _install_direct(storage, server_id="beta", env={"TOKEN": "two"})
    with storage.transaction() as conn:
        release = _fake_release(storage.data_dir)
        mcp.install_server(
            conn,
            warden.install_request_for(storage.data_dir, release),
            mcp.McpCatalog(servers=[]),
        )
        result = warden.sync_registry(conn, storage.data_dir)

    assert result.indexed_stdio_servers == ["alpha"]
    assert result.skipped_conflicting_env_servers == ["beta"]
    assert mcp.get_server(storage.conn, warden.WARDEN_SERVER_ID).env["TOKEN"] == "one"


def test_marketplace_changes_auto_sync_and_preserve_warden_owned_entries(
    tmp_path: Path, monkeypatch
) -> None:
    storage, client = _harness(tmp_path)
    release = _fake_release(storage.data_dir)
    monkeypatch.setattr(warden, "install_pinned_warden", lambda _data_dir: release)
    assert client.post("/api/v1/mcp-servers/install", json={"catalog_id": "warden"}).status_code == 201

    config_path = warden.warden_config_path(storage.data_dir)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["mcp_servers"]["manual-tool"] = {"command": "manual", "args": []}
    config_path.write_text(json.dumps(config), encoding="utf-8")

    assert client.post("/api/v1/mcp-servers/install", json={"catalog_id": "memory"}).status_code == 201
    after_install = json.loads(config_path.read_text(encoding="utf-8"))["mcp_servers"]
    assert set(after_install) == {"manual-tool", "memory"}

    assert client.delete("/api/v1/mcp-servers/memory").status_code == 204
    after_delete = json.loads(config_path.read_text(encoding="utf-8"))["mcp_servers"]
    assert set(after_delete) == {"manual-tool"}


def test_rollback_switches_to_previous_verified_release_and_keeps_direct_servers(tmp_path: Path) -> None:
    storage, client = _harness(tmp_path)
    _install_direct(storage, server_id="memory")
    current = _fake_release(storage.data_dir, verified_at="2026-07-31T12:00:00+00:00")
    previous = _fake_release(
        storage.data_dir,
        version="0.2.0",
        commit="1" * 40,
        verified_at="2026-07-30T12:00:00+00:00",
    )
    with storage.transaction() as conn:
        mcp.install_server(
            conn,
            warden.install_request_for(storage.data_dir, current),
            mcp.McpCatalog(servers=[]),
        )
        warden.sync_registry(conn, storage.data_dir)

    before = client.get("/api/v1/mcp-servers/warden/status").json()
    assert before["rollback_available"] is True

    response = client.post("/api/v1/mcp-servers/warden/rollback")

    assert response.status_code == 200, response.text
    assert response.json()["active_version"] == "0.2.0"
    assert mcp.get_server(storage.conn, warden.WARDEN_SERVER_ID).command == previous.python_command
    direct = mcp.build_mcp_config(mcp.list_servers(storage.conn))["mcpServers"]
    assert set(direct) == {"memory", "warden"}
