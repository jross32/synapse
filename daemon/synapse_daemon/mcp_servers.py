"""Local MCP-server marketplace + manager (ADR-0017, MW2).

Two kinds of MCP server:
- **stdio** (most of them): the AI launches the command on demand. Synapse just
  stores the command and injects it into the AI session's ``.mcp.json``.
- **http** (e.g. the owner's web-scraper): a standalone server that must be
  *running*. Synapse health-checks it (is the port listening?), can launch it
  (if a launch command is configured), autoruns it on boot if enabled, and wires
  its URL into the AI session.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .errors import conflict, invalid, not_found
from .runtime_paths import bundled_mcp_servers_sample, repo_root
from .secrets import SECRET_PLACEHOLDER
from .time_utils import to_iso, utc_now

WEB_SCRAPER_SERVER_ID = "web-scraper"
WEB_SCRAPER_LEGACY_SERVER_ID = "wbscrper"
WEB_SCRAPER_KNOWN_IDS = (WEB_SCRAPER_SERVER_ID, WEB_SCRAPER_LEGACY_SERVER_ID)
WEB_SCRAPER_GIT_URL = "https://github.com/jross32/wbscrper.git"
WEB_SCRAPER_DEFAULT_URL = "http://127.0.0.1:12345/mcp"


class McpTransport(str, Enum):
    STDIO = "stdio"
    HTTP = "http"


class McpServerStatus(str, Enum):
    STDIO_READY = "stdio_ready"  # launched by the AI on demand
    STOPPED = "stopped"          # http server, nothing listening
    STARTING = "starting"
    CONNECTED = "connected"      # http server is up
    ERROR = "error"


class McpCatalogEntry(BaseModel):
    id: str
    name: str
    publisher: str | None = None
    description: str = ""
    transport: McpTransport = McpTransport.STDIO
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    launch_command: str | None = None
    launch_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    recommended: bool = False
    installed: bool = False


class McpCatalog(BaseModel):
    version: int = 1
    generated_at: str | None = None
    servers: list[McpCatalogEntry] = Field(default_factory=list)


class McpServer(BaseModel):
    id: str
    name: str
    publisher: str | None = None
    description: str = ""
    transport: McpTransport
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    launch_command: str | None = None
    launch_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    autorun: bool = False
    created_at: str
    updated_at: str


class McpServerView(McpServer):
    status: McpServerStatus = McpServerStatus.STOPPED
    detail: str | None = None


class McpServerList(BaseModel):
    servers: list[McpServerView] = Field(default_factory=list)


class McpServerInstallRequest(BaseModel):
    """Install from the catalog (``catalog_id``) or a full custom config."""

    catalog_id: str | None = None
    id: str | None = None
    name: str | None = None
    publisher: str | None = None
    description: str = ""
    transport: McpTransport | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    launch_command: str | None = None
    launch_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class McpServerUpdate(BaseModel):
    enabled: bool | None = None
    autorun: bool | None = None
    url: str | None = None
    launch_command: str | None = None
    launch_args: list[str] | None = None
    env: dict[str, str] | None = None


def preferred_npm_command() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def web_scraper_install_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "vendor" / "web-scraper"


def looks_like_web_scraper_repo(path: Path) -> bool:
    candidate = Path(path)
    if not (candidate / "mcp-server.js").exists():
        return False
    package_json = candidate / "package.json"
    if not package_json.exists():
        return False
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    scripts = payload.get("scripts")
    return isinstance(scripts, dict) and isinstance(scripts.get("mcp:http"), str)


def discover_local_web_scraper_repo() -> Path | None:
    candidates = (
        repo_root().parent / "wbscrper",
        Path.home() / "wbscrper",
        Path("C:/Users/justi/wbscrper"),
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if looks_like_web_scraper_repo(resolved):
            return resolved
    return None


def find_known_web_scraper_server(conn: sqlite3.Connection) -> McpServer | None:
    for server_id in WEB_SCRAPER_KNOWN_IDS:
        row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
        if row is not None:
            return _row_to_server(row)
    return None


def _run_setup_command(args: list[str], *, cwd: Path, step: str) -> None:
    try:
        completed = subprocess.run(  # noqa: S603 -- trusted bootstrap commands
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except FileNotFoundError as exc:
        raise invalid(
            "mcp_server",
            f"Could not {step} because `{args[0]}` is not installed or not on PATH.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise invalid("mcp_server", f"Could not {step}: {exc}") from exc
    if completed.returncode == 0:
        return
    tail = "\n".join(
        line for line in (completed.stderr or completed.stdout or "").splitlines()[-8:] if line.strip()
    )
    detail = f" {tail}" if tail else ""
    raise invalid("mcp_server", f"Could not {step}.{detail}")


def ensure_web_scraper_checkout(data_dir: Path) -> Path:
    target = web_scraper_install_dir(Path(data_dir))
    if looks_like_web_scraper_repo(target):
        return target
    if target.exists() and any(target.iterdir()):
        raise invalid(
            "mcp_server",
            f"The Web Scraper install folder already exists at {target}, but it does not look like the official repo.",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    _run_setup_command(
        ["git", "clone", WEB_SCRAPER_GIT_URL, str(target)],
        cwd=target.parent,
        step="download the Web Scraper MCP from GitHub",
    )
    if not looks_like_web_scraper_repo(target):
        raise invalid(
            "mcp_server",
            f"The downloaded Web Scraper bundle at {target} is missing its MCP entrypoint.",
        )
    if not (target / "node_modules").exists():
        _run_setup_command(
            [preferred_npm_command(), "install"],
            cwd=target,
            step="install the Web Scraper MCP dependencies",
        )
    return target


def web_scraper_install_request(source_path: Path) -> McpServerInstallRequest:
    return McpServerInstallRequest(
        id=WEB_SCRAPER_SERVER_ID,
        name="Web Scraper",
        publisher="The WhatIf Company",
        description=(
            "First-party Web Scraper MCP + UI, downloaded from GitHub and "
            "wired into Synapse as a native installed page."
        ),
        transport=McpTransport.HTTP,
        url=WEB_SCRAPER_DEFAULT_URL,
        launch_command=preferred_npm_command(),
        launch_args=["--prefix", str(source_path), "run", "mcp:http"],
    )


def ensure_bootstrap_web_scraper(
    conn: sqlite3.Connection,
    *,
    source_path: Path | None = None,
) -> McpServer | None:
    source = source_path or discover_local_web_scraper_repo()
    if source is None or not looks_like_web_scraper_repo(source):
        return None

    server = find_known_web_scraper_server(conn)
    desired = web_scraper_install_request(source)
    if server is None:
        server = install_server(conn, desired, McpCatalog(servers=[]))
    elif server.transport != McpTransport.HTTP:
        delete_server(conn, server.id)
        server = install_server(conn, desired, McpCatalog(servers=[]))

    patch_kwargs: dict[str, object] = {}
    if server.url != desired.url:
        patch_kwargs["url"] = desired.url
    if server.launch_command != desired.launch_command:
        patch_kwargs["launch_command"] = desired.launch_command
    if server.launch_args != desired.launch_args:
        patch_kwargs["launch_args"] = desired.launch_args
    if not server.enabled:
        patch_kwargs["enabled"] = True
    if not server.autorun:
        patch_kwargs["autorun"] = True
    if patch_kwargs:
        server = update_server(conn, server.id, McpServerUpdate(**patch_kwargs))
    return server


def _loads(value: str | None, default):  # noqa: ANN001
    try:
        return json.loads(value) if value else default
    except Exception:  # noqa: BLE001
        return default


def _row_to_server(row: sqlite3.Row) -> McpServer:
    return McpServer(
        id=row["id"],
        name=row["name"],
        publisher=row["publisher"],
        description=row["description"] or "",
        transport=McpTransport(row["transport"]),
        command=row["command"],
        args=_loads(row["args_json"], []),
        url=row["url"],
        launch_command=row["launch_command"],
        launch_args=_loads(row["launch_args_json"], []),
        env=_loads(row["env_json"], {}),
        enabled=bool(row["enabled"]),
        autorun=bool(row["autorun"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def load_catalog(installed_ids: set[str]) -> McpCatalog:
    path = bundled_mcp_servers_sample()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return McpCatalog(servers=[])
    entries: list[McpCatalogEntry] = []
    for item in raw.get("servers", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        try:
            entry = McpCatalogEntry(**item)
        except Exception:  # noqa: BLE001
            continue
        entry.installed = entry.id in installed_ids
        entries.append(entry)
    return McpCatalog(version=raw.get("version", 1), generated_at=raw.get("generated_at"), servers=entries)


# ── Secret redaction (env may hold tokens, e.g. a GitHub PAT) ────────────────


def _redact_env(env: dict[str, str]) -> dict[str, str]:
    """Replace every non-empty env value with the placeholder. MCP env is
    typically credentials, so the daemon never round-trips real values to a
    client -- mirrors the project env-var contract (secrets.redact)."""
    return {k: (SECRET_PLACEHOLDER if v else v) for k, v in env.items()}


def client_dump(server: McpServer) -> dict:
    """Serialize a server for an API client with env secrets redacted."""
    data = server.model_dump(mode="json")
    data["env"] = _redact_env(server.env)
    return data


# ── CRUD ─────────────────────────────────────────────────────────────────────


def list_servers(conn: sqlite3.Connection) -> list[McpServer]:
    rows = conn.execute("SELECT * FROM mcp_servers ORDER BY name").fetchall()
    return [_row_to_server(r) for r in rows]


def get_server(conn: sqlite3.Connection, server_id: str) -> McpServer:
    row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
    if row is None:
        raise not_found("mcp_server", server_id)
    return _row_to_server(row)


def install_server(conn: sqlite3.Connection, payload: McpServerInstallRequest, catalog: McpCatalog) -> McpServer:
    if payload.catalog_id:
        entry = next((e for e in catalog.servers if e.id == payload.catalog_id), None)
        if entry is None:
            raise not_found("mcp_catalog", payload.catalog_id)
        cfg: McpCatalogEntry | McpServerInstallRequest = entry
        server_id = entry.id
    else:
        if not payload.id or not payload.name:
            raise invalid("mcp_server", "A custom MCP server needs at least an id and a name.")
        cfg = payload
        server_id = payload.id

    if conn.execute("SELECT id FROM mcp_servers WHERE id = ?", (server_id,)).fetchone():
        raise conflict("mcp_server", f"MCP server '{server_id}' is already installed.")

    transport = cfg.transport or McpTransport.STDIO
    now = to_iso(utc_now())
    conn.execute(
        "INSERT INTO mcp_servers (id, name, publisher, description, transport, command, args_json, url, "
        "launch_command, launch_args_json, env_json, enabled, autorun, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            server_id,
            cfg.name or server_id,
            getattr(cfg, "publisher", None),
            getattr(cfg, "description", "") or "",
            transport.value if isinstance(transport, McpTransport) else transport,
            cfg.command,
            json.dumps(cfg.args or []),
            cfg.url,
            cfg.launch_command,
            json.dumps(cfg.launch_args or []),
            json.dumps(getattr(cfg, "env", {}) or {}),
            1,
            0,
            now,
            now,
        ),
    )
    return get_server(conn, server_id)


def update_server(conn: sqlite3.Connection, server_id: str, patch: McpServerUpdate) -> McpServer:
    current = get_server(conn, server_id)  # 404 if missing
    fields = patch.model_dump(exclude_unset=True)
    # A redacted env value coming back from the client ("(set)") means "keep the
    # stored secret" -- never overwrite a real token with the placeholder.
    if "env" in fields and isinstance(fields["env"], dict):
        fields["env"] = {
            k: (current.env.get(k, "") if v == SECRET_PLACEHOLDER else v)
            for k, v in fields["env"].items()
        }
    col_map = {"args": "args_json", "launch_args": "launch_args_json", "env": "env_json"}
    sets: list[str] = []
    args: list[object] = []
    for key, value in fields.items():
        if key in ("enabled", "autorun"):
            value = 1 if value else 0
        elif key in ("launch_args", "env"):
            value = json.dumps(value)
        sets.append(f"{col_map.get(key, key)} = ?")
        args.append(value)
    if sets:
        sets.append("updated_at = ?")
        args.append(to_iso(utc_now()))
        args.append(server_id)
        conn.execute(f"UPDATE mcp_servers SET {', '.join(sets)} WHERE id = ?", args)
    return get_server(conn, server_id)


def delete_server(conn: sqlite3.Connection, server_id: str) -> None:
    get_server(conn, server_id)
    conn.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))


def build_mcp_config(servers: list[McpServer], allow_ids: list[str] | None = None) -> dict:
    """A Claude-compatible ``.mcp.json`` from the user's enabled servers.

    ``allow_ids`` scopes which servers to include (per-role binding, ADR-0025):
    ``None`` -> all enabled (default); a list -> only servers whose id is in it
    (so an empty list yields no servers)."""
    out: dict[str, dict] = {}
    for s in servers:
        if not s.enabled:
            continue
        if allow_ids is not None and s.id not in allow_ids:
            continue
        if s.transport == McpTransport.HTTP and s.url:
            out[s.id] = {"type": "http", "url": s.url}
        elif s.command:
            entry: dict = {"command": s.command, "args": s.args}
            if s.env:
                entry["env"] = s.env
            out[s.id] = entry
    return {"mcpServers": out}


# ── Process manager (status + launch for http servers) ───────────────────────


class McpServerManager:
    """Launches + health-checks standalone (http) MCP servers. stdio servers are
    the AI's to launch, so they report a static 'ready' state."""

    def __init__(self) -> None:
        self._procs: dict[str, subprocess.Popen] = {}

    async def _port_open(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.5)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            return True
        except Exception:  # noqa: BLE001 -- not listening / bad url
            return False

    async def status(self, server: McpServer) -> tuple[McpServerStatus, str | None]:
        if server.transport == McpTransport.STDIO:
            return McpServerStatus.STDIO_READY, "Launched by your AI when needed."
        if not server.url:
            return McpServerStatus.STOPPED, "No URL configured."
        proc = self._procs.get(server.id)
        we_launched = proc is not None and proc.poll() is None
        if await self._port_open(server.url):
            return McpServerStatus.CONNECTED, None
        if we_launched:
            return McpServerStatus.STARTING, "Starting…"
        return McpServerStatus.STOPPED, "Not running — launch it or start it yourself."

    def start(self, server: McpServer) -> bool:
        """Spawn the configured launch command for an http server. Returns True
        if a process is (now) running."""
        if server.transport != McpTransport.HTTP or not server.launch_command:
            return False
        existing = self._procs.get(server.id)
        if existing and existing.poll() is None:
            return True
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        try:
            proc = subprocess.Popen(  # noqa: S603 -- user-configured launch command
                [server.launch_command, *server.launch_args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                start_new_session=(sys.platform != "win32"),
                env={**os.environ, **server.env},
            )
            self._procs[server.id] = proc
            return True
        except Exception:  # noqa: BLE001
            return False

    def _terminate(self, proc: subprocess.Popen) -> None:
        """Terminate a launched server *and its descendants*. Wrapper launchers
        (npx/uvx/node) put the real listener in a child; killing only the parent
        orphans it and the port stays bound. Mirrors
        process_manager._terminate_tree, then reaps so no zombie is left."""
        try:
            import psutil  # lazy: a missing psutil only degrades stop, not import
        except Exception:  # noqa: BLE001
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            root = psutil.Process(proc.pid)
        except Exception:  # noqa: BLE001 -- already gone
            return
        procs = [root]
        try:
            procs.extend(root.children(recursive=True))
        except Exception:  # noqa: BLE001
            pass
        for p in procs:
            try:
                p.terminate()
            except Exception:  # noqa: BLE001
                pass
        _gone, alive = psutil.wait_procs(procs, timeout=5.0)
        for p in alive:
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass
        psutil.wait_procs(alive, timeout=2.0)
        try:
            proc.wait(timeout=1)  # reap the Popen handle too
        except Exception:  # noqa: BLE001
            pass

    def stop(self, server_id: str) -> bool:
        proc = self._procs.pop(server_id, None)
        if proc is None:
            return False
        self._terminate(proc)
        return True

    async def shutdown(self) -> None:
        for proc in list(self._procs.values()):
            self._terminate(proc)
        self._procs.clear()


async def server_views(conn: sqlite3.Connection, manager: McpServerManager) -> list[McpServerView]:
    views: list[McpServerView] = []
    for server in list_servers(conn):
        status, detail = await manager.status(server)
        data = server.model_dump()
        data["env"] = _redact_env(server.env)  # never round-trip real secrets
        views.append(McpServerView(**data, status=status, detail=detail))
    return views
