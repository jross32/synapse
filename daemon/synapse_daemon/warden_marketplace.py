"""Version-pinned Warden marketplace installation and registry sync.

Warden remains an optional MCP server beside every directly configured MCP
server.  Synapse owns the downloaded checkout and virtual environment, verifies
the immutable upstream commit before activation, and keeps old verified
releases so a later catalog update can be rolled back.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .errors import SynapseError, conflict, invalid
from .mcp_servers import McpServer, McpTransport, get_server
from .time_utils import to_iso, utc_now

WARDEN_SERVER_ID = "warden"
WARDEN_SOURCE_URL = "https://github.com/chris-asmussen/warden.git"
WARDEN_PINNED_VERSION = "0.2.1"
WARDEN_PINNED_COMMIT = "29cb1355c33f19e8c9c6c6d48ba3136234eeaf2c"
WARDEN_RELEASE_MANIFEST = "synapse-release.json"
WARDEN_RESERVED_ENV = {"WARDEN_HOME", "WARDEN_CONFIG"}


class WardenRelease(BaseModel):
    version: str
    commit: str
    source_url: str
    release_dir: str
    python_command: str
    verified_at: str


class WardenRegistrySync(BaseModel):
    synced_at: str
    indexed_stdio_servers: list[str] = Field(default_factory=list)
    skipped_http_servers: list[str] = Field(default_factory=list)
    skipped_disabled_servers: list[str] = Field(default_factory=list)
    skipped_conflicting_env_servers: list[str] = Field(default_factory=list)
    config_path: str


class WardenStatus(BaseModel):
    installed: bool
    cached: bool
    verified: bool
    pinned_version: str = WARDEN_PINNED_VERSION
    pinned_commit: str = WARDEN_PINNED_COMMIT
    active_version: str | None = None
    active_commit: str | None = None
    source_url: str = WARDEN_SOURCE_URL
    install_path: str | None = None
    update_available: bool = False
    rollback_available: bool = False
    rollback_version: str | None = None
    registry: WardenRegistrySync | None = None


def warden_root(data_dir: Path) -> Path:
    return Path(data_dir) / "vendor" / "mcp" / WARDEN_SERVER_ID


def release_slug(version: str, commit: str) -> str:
    return f"{version}-{commit[:12]}"


def pinned_release_dir(data_dir: Path) -> Path:
    return warden_root(data_dir) / "releases" / release_slug(
        WARDEN_PINNED_VERSION, WARDEN_PINNED_COMMIT
    )


def warden_config_path(data_dir: Path) -> Path:
    return warden_root(data_dir) / "state" / "config.json"


def _venv_python(release_dir: Path) -> Path:
    if os.name == "nt":
        return release_dir / ".venv" / "Scripts" / "python.exe"
    return release_dir / ".venv" / "bin" / "python"


def _python_bootstrap_command() -> list[str]:
    """Return a real Python interpreter capable of creating a virtualenv.

    In source mode the daemon interpreter is ideal.  A packaged PyInstaller
    executable is not a general Python CLI, so packaged installs use an
    explicitly installed Python 3.10+ discovered on PATH.
    """

    if not bool(getattr(sys, "frozen", False)):
        return [sys.executable]
    py_launcher = shutil.which("py")
    if py_launcher:
        return [py_launcher, "-3"]
    for name in ("python", "python3"):
        candidate = shutil.which(name)
        if candidate:
            return [candidate]
    raise SynapseError(
        "warden.python_missing",
        "Warden requires Python 3.10 or newer. Install Python, then retry the marketplace download.",
        retryable=True,
        status=503,
    )


def _manifest_path(release_dir: Path) -> Path:
    return release_dir / WARDEN_RELEASE_MANIFEST


def _remove_tree(path: Path) -> None:
    """Remove one validated install directory, including read-only Git files."""

    def _make_writable_and_retry(function, target, _error) -> None:  # noqa: ANN001
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=_make_writable_and_retry)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _run(command: list[str], *, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError as exc:
        raise SynapseError(
            "warden.install_dependency_missing",
            f"Warden could not be installed because '{command[0]}' is unavailable.",
            details={"command": command[0]},
            status=503,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SynapseError(
            "warden.install_timeout",
            "Warden installation timed out before verification completed.",
            details={"step": command[:3]},
            retryable=True,
            status=504,
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-2000:]
        raise SynapseError(
            "warden.install_failed",
            "Warden could not be downloaded and verified.",
            details={"step": command[:3], "output": detail},
            retryable=True,
            status=502,
        ) from exc


def load_release(release_dir: Path) -> WardenRelease | None:
    manifest = _manifest_path(release_dir)
    try:
        release = WardenRelease.model_validate_json(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    python_command = Path(release.python_command)
    if re.fullmatch(r"[0-9a-f]{40}", release.commit) is None:
        return None
    if not python_command.is_file():
        return None
    return release


def list_verified_releases(data_dir: Path) -> list[WardenRelease]:
    releases_dir = warden_root(data_dir) / "releases"
    if not releases_dir.is_dir():
        return []
    found = [release for child in releases_dir.iterdir() if (release := load_release(child)) is not None]
    return sorted(found, key=lambda item: item.verified_at, reverse=True)


def install_pinned_warden(data_dir: Path) -> WardenRelease:
    """Download, install, and verify the catalog-pinned Warden release.

    A release is never returned to the caller until its Git HEAD, package
    version, import, and CLI entry point have all been verified.
    """

    release_dir = pinned_release_dir(data_dir)
    existing = load_release(release_dir)
    if existing is not None and existing.commit == WARDEN_PINNED_COMMIT:
        return existing

    root = warden_root(data_dir).resolve()
    release_dir = release_dir.resolve()
    if root not in release_dir.parents:
        raise invalid("warden", "Resolved Warden release path escaped Synapse's vendor directory.")
    if release_dir.exists():
        _remove_tree(release_dir)
    release_dir.parent.mkdir(parents=True, exist_ok=True)
    source_dir = release_dir / "source"
    try:
        _run(["git", "clone", "--filter=blob:none", "--no-checkout", WARDEN_SOURCE_URL, str(source_dir)], timeout=180)
        _run(["git", "checkout", "--detach", WARDEN_PINNED_COMMIT], cwd=source_dir, timeout=120)
        head = _run(["git", "rev-parse", "HEAD"], cwd=source_dir, timeout=30).stdout.strip().lower()
        if head != WARDEN_PINNED_COMMIT:
            raise SynapseError(
                "warden.commit_mismatch",
                "Downloaded Warden source did not match Synapse's pinned commit.",
                details={"expected": WARDEN_PINNED_COMMIT, "actual": head},
                status=409,
            )
        python_command = _venv_python(release_dir)
        _run([*_python_bootstrap_command(), "-m", "venv", str(release_dir / ".venv")], timeout=180)
        _run(
            [str(python_command), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", str(source_dir)],
            timeout=600,
        )
        check = (
            "import warden, warden.server; "
            f"assert warden.__version__ == {WARDEN_PINNED_VERSION!r}, warden.__version__; "
            "print(warden.__version__)"
        )
        _run([str(python_command), "-c", check], timeout=60)
        _run([str(python_command), "-m", "warden", "--help"], timeout=60)
        release = WardenRelease(
            version=WARDEN_PINNED_VERSION,
            commit=WARDEN_PINNED_COMMIT,
            source_url=WARDEN_SOURCE_URL,
            release_dir=str(release_dir),
            python_command=str(python_command),
            verified_at=to_iso(utc_now()),
        )
        _atomic_json(_manifest_path(release_dir), release.model_dump(mode="json"))
        return release
    except Exception:
        if release_dir.exists() and load_release(release_dir) is None:
            _remove_tree(release_dir)
        raise


def install_request_for(data_dir: Path, release: WardenRelease):  # noqa: ANN201
    # Local import avoids a module cycle at import time.
    from .mcp_servers import McpServerInstallRequest

    config_path = warden_config_path(data_dir)
    return McpServerInstallRequest(
        id=WARDEN_SERVER_ID,
        name="Warden",
        publisher="Chris Asmussen",
        description=(
            "Search and route across many MCP servers through five compact tools. "
            "Optional: direct Synapse MCP access remains available."
        ),
        transport=McpTransport.STDIO,
        command=release.python_command,
        args=["-m", "warden", "serve"],
        env={
            "WARDEN_HOME": str(config_path.parent),
            "WARDEN_CONFIG": str(config_path),
        },
    )


def activate_release(conn: sqlite3.Connection, data_dir: Path, release: WardenRelease) -> McpServer:
    get_server(conn, WARDEN_SERVER_ID)
    config_path = warden_config_path(data_dir)
    conn.execute(
        "UPDATE mcp_servers SET command = ?, args_json = ?, updated_at = ? WHERE id = ?",
        (
            release.python_command,
            json.dumps(["-m", "warden", "serve"]),
            to_iso(utc_now()),
            WARDEN_SERVER_ID,
        ),
    )
    # Registry sync will merge downstream credentials with these reserved vars.
    conn.execute(
        "UPDATE mcp_servers SET env_json = ? WHERE id = ?",
        (
            json.dumps({"WARDEN_HOME": str(config_path.parent), "WARDEN_CONFIG": str(config_path)}),
            WARDEN_SERVER_ID,
        ),
    )
    return get_server(conn, WARDEN_SERVER_ID)


def _write_registry(
    data_dir: Path,
    registry: dict[str, dict[str, Any]],
    *,
    sync_details: dict[str, Any],
) -> str:
    path = warden_config_path(data_dir)
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, ValueError):
            existing = {}
    prior_managed = set((existing.get("_synapse") or {}).get("managed_server_ids", []))
    existing_servers = existing.get("mcp_servers") or {}
    unmanaged_servers = {
        key: value
        for key, value in existing_servers.items()
        if key not in prior_managed and key not in registry
    }
    payload = {
        "mcp_servers": {**unmanaged_servers, **registry},
        "skill_dirs": existing.get("skill_dirs", []),
        "migrations": existing.get("migrations", []),
        "routing": existing.get("routing", {}),
        "_synapse": {
            "managed_server_ids": sorted(registry),
            **sync_details,
        },
    }
    _atomic_json(path, payload)
    return str(path)


def sync_registry(conn: sqlite3.Connection, data_dir: Path) -> WardenRegistrySync:
    """Mirror enabled stdio servers into Warden without replacing direct access.

    Secrets are not copied into Warden's JSON registry.  They are inherited by
    Warden from its Synapse MCP process environment, keeping Synapse as the only
    credential store used by this integration.
    """

    get_server(conn, WARDEN_SERVER_ID)
    rows = conn.execute("SELECT * FROM mcp_servers ORDER BY id").fetchall()
    registry: dict[str, dict[str, Any]] = {}
    aggregate_env = {
        "WARDEN_HOME": str(warden_config_path(data_dir).parent),
        "WARDEN_CONFIG": str(warden_config_path(data_dir)),
    }
    indexed: list[str] = []
    skipped_http: list[str] = []
    skipped_disabled: list[str] = []
    skipped_conflicts: list[str] = []

    for row in rows:
        server_id = str(row["id"])
        if server_id == WARDEN_SERVER_ID:
            continue
        if not bool(row["enabled"]):
            skipped_disabled.append(server_id)
            continue
        if row["transport"] != McpTransport.STDIO.value or not row["command"]:
            skipped_http.append(server_id)
            continue
        server_env = json.loads(row["env_json"] or "{}")
        has_conflict = any(
            key in WARDEN_RESERVED_ENV
            or (key in aggregate_env and aggregate_env[key] != value)
            for key, value in server_env.items()
        )
        if has_conflict:
            skipped_conflicts.append(server_id)
            continue
        aggregate_env.update(server_env)
        registry[server_id] = {
            "command": row["command"],
            "args": json.loads(row["args_json"] or "[]"),
        }
        indexed.append(server_id)

    synced_at = to_iso(utc_now())
    config_path = _write_registry(
        data_dir,
        registry,
        sync_details={
            "synced_at": synced_at,
            "skipped_http_servers": skipped_http,
            "skipped_disabled_servers": skipped_disabled,
            "skipped_conflicting_env_servers": skipped_conflicts,
        },
    )
    conn.execute(
        "UPDATE mcp_servers SET env_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(aggregate_env), to_iso(utc_now()), WARDEN_SERVER_ID),
    )
    return WardenRegistrySync(
        synced_at=synced_at,
        indexed_stdio_servers=indexed,
        skipped_http_servers=skipped_http,
        skipped_disabled_servers=skipped_disabled,
        skipped_conflicting_env_servers=skipped_conflicts,
        config_path=config_path,
    )


def sync_if_installed(conn: sqlite3.Connection, data_dir: Path) -> WardenRegistrySync | None:
    row = conn.execute("SELECT id FROM mcp_servers WHERE id = ?", (WARDEN_SERVER_ID,)).fetchone()
    if row is None:
        return None
    return sync_registry(conn, data_dir)


def _active_release(conn: sqlite3.Connection, data_dir: Path) -> WardenRelease | None:
    try:
        server = get_server(conn, WARDEN_SERVER_ID)
    except SynapseError:
        return None
    command = str(Path(server.command).resolve()) if server.command else ""
    return next(
        (
            release
            for release in list_verified_releases(data_dir)
            if str(Path(release.python_command).resolve()) == command
        ),
        None,
    )


def status(conn: sqlite3.Connection, data_dir: Path) -> WardenStatus:
    releases = list_verified_releases(data_dir)
    installed = conn.execute(
        "SELECT 1 FROM mcp_servers WHERE id = ?", (WARDEN_SERVER_ID,)
    ).fetchone() is not None
    active = _active_release(conn, data_dir)
    config_path = warden_config_path(data_dir)
    registry_sync: WardenRegistrySync | None = None
    if config_path.exists():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            synapse_meta = payload.get("_synapse") or {}
            configured = sorted(synapse_meta.get("managed_server_ids", []))
            direct_rows = conn.execute("SELECT id, enabled, transport FROM mcp_servers ORDER BY id").fetchall()
            registry_sync = WardenRegistrySync(
                synced_at=synapse_meta.get("synced_at")
                or to_iso(datetime.fromtimestamp(config_path.stat().st_mtime, tz=UTC)),
                indexed_stdio_servers=configured,
                skipped_http_servers=synapse_meta.get("skipped_http_servers")
                or [
                    str(row["id"])
                    for row in direct_rows
                    if row["id"] != WARDEN_SERVER_ID and row["enabled"] and row["transport"] == "http"
                ],
                skipped_disabled_servers=synapse_meta.get("skipped_disabled_servers")
                or [
                    str(row["id"])
                    for row in direct_rows
                    if row["id"] != WARDEN_SERVER_ID and not row["enabled"]
                ],
                skipped_conflicting_env_servers=synapse_meta.get("skipped_conflicting_env_servers") or [],
                config_path=str(config_path),
            )
        except (OSError, ValueError):
            registry_sync = None
    previous = next((release for release in releases if active is None or release.commit != active.commit), None)
    return WardenStatus(
        installed=installed,
        cached=bool(releases),
        verified=active is not None,
        active_version=active.version if active else None,
        active_commit=active.commit if active else None,
        install_path=active.release_dir if active else None,
        update_available=bool(installed and (active is None or active.commit != WARDEN_PINNED_COMMIT)),
        rollback_available=bool(installed and previous),
        rollback_version=previous.version if previous else None,
        registry=registry_sync,
    )


def rollback(conn: sqlite3.Connection, data_dir: Path) -> WardenRelease:
    active = _active_release(conn, data_dir)
    previous = next(
        (
            release
            for release in list_verified_releases(data_dir)
            if active is None or release.commit != active.commit
        ),
        None,
    )
    if previous is None:
        raise conflict("warden", "No previous verified Warden release is available to restore.")
    activate_release(conn, data_dir, previous)
    sync_registry(conn, data_dir)
    return previous
