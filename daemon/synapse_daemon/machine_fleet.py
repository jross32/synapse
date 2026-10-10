"""Cross-platform identity and capability snapshot for an installed Synapse host."""

from __future__ import annotations

import json
import os
import platform
import socket
import uuid
from pathlib import Path

from .storage import Storage
from .time_utils import to_iso, utc_now

MACHINE_ID_FILENAME = "machine-id"


def ensure_machine_id(data_dir: Path) -> str:
    path = Path(data_dir) / MACHINE_ID_FILENAME
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = str(uuid.uuid4())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    return value


def local_capabilities() -> list[str]:
    caps = ["daemon", "mcp", "projects", "ai-context"]
    if os.name == "nt":
        caps.extend(["desktop-control", "windows"])
    elif platform.system().lower() == "darwin":
        caps.append("macos")
    else:
        caps.append("linux")
    return sorted(set(caps))


def upsert_local_machine(storage: Storage, data_dir: Path, version: str | None = None, name: str | None = None) -> dict:
    machine_id = ensure_machine_id(data_dir)
    now = to_iso(utc_now())
    hostname = socket.gethostname() or "Synapse host"
    system = platform.system().lower() or "unknown"
    arch = platform.machine().lower() or "unknown"
    caps = local_capabilities()
    with storage.transaction() as conn:
        existing = conn.execute("SELECT created_at,name,revoked FROM synapse_machines WHERE id = ?", (machine_id,)).fetchone()
        if existing and existing["revoked"]:
            from .errors import SynapseError
            raise SynapseError(code="machine.revoked", message="Machine access has been revoked.", status=403)
        created = existing["created_at"] if existing else now
        # Heartbeats should never overwrite a user's friendly machine name.
        # Explicit names are still accepted on first registration or a deliberate update.
        machine_name = ((name if name is not None else existing["name"] if existing else hostname) or "").strip() or hostname
        conn.execute(
            """INSERT INTO synapse_machines
               (id,name,platform,architecture,hostname,synapse_version,capabilities_json,created_at,last_seen_at,revoked)
               VALUES (?,?,?,?,?,?,?,?,?,0)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, platform=excluded.platform,
                 architecture=excluded.architecture, hostname=excluded.hostname,
                 synapse_version=excluded.synapse_version,
                 capabilities_json=excluded.capabilities_json,
                 last_seen_at=excluded.last_seen_at""",
            (machine_id,machine_name,system,arch,hostname,version,json.dumps(caps),created,now),
        )
    return {
        "id": machine_id, "name": machine_name, "platform": system,
        "architecture": arch, "hostname": hostname, "synapse_version": version,
        "capabilities": caps, "created_at": created, "last_seen_at": now, "online": True,
    }


def list_machines(storage: Storage) -> list[dict]:
    rows = storage.conn.execute(
        """SELECT id,name,platform,architecture,hostname,synapse_version,
                  capabilities_json,created_at,last_seen_at
           FROM synapse_machines WHERE revoked=0 ORDER BY name COLLATE NOCASE,id"""
    ).fetchall()
    return [{
        "id": r["id"], "name": r["name"], "platform": r["platform"],
        "architecture": r["architecture"], "hostname": r["hostname"],
        "synapse_version": r["synapse_version"],
        "capabilities": json.loads(r["capabilities_json"] or "[]"),
        "created_at": r["created_at"], "last_seen_at": r["last_seen_at"],
    } for r in rows]
