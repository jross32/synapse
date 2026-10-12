"""Account-isolated storage connection metadata.

Metadata only: OAuth secrets must be stored in an OS credential vault later.
No provider can be treated as connected until a verified principal is provided.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import os
import tempfile
import threading

PROVIDERS = frozenset({"google_drive", "icloud"})
STATES = frozenset({"pending", "connected", "reauth_required", "disconnected"})


@dataclass(frozen=True)
class Connection:
    account_id: str
    provider: str
    connection_id: str
    status: str
    remote_account_hint: str = ""

    def public(self) -> dict:
        return asdict(self)


def verified_account_id(identity: dict | None) -> str:
    """Fail closed on missing/unverified account identities."""
    if not isinstance(identity, dict):
        raise PermissionError("Verified account identity is required")
    account_id = identity.get("account_id")
    if identity.get("verified") is not True or not isinstance(account_id, str) or not account_id.strip():
        raise PermissionError("Verified account identity is required")
    return account_id.strip()


class ConnectionRegistry:
    """Thread-safe metadata registry; never stores OAuth tokens or passwords."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".storage-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(rows, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def list_for_account(self, identity: dict) -> list[dict]:
        owner = verified_account_id(identity)
        with self._lock:
            return [r.copy() for r in self._load() if r["account_id"] == owner]

    def upsert(self, identity: dict, connection: Connection) -> dict:
        owner = verified_account_id(identity)
        if connection.account_id != owner:
            raise PermissionError("Account does not own connection")
        if connection.provider not in PROVIDERS or connection.status not in STATES:
            raise ValueError("Invalid provider or state")
        if not connection.connection_id or not connection.connection_id.strip():
            raise ValueError("Missing connection id")
        with self._lock:
            rows = self._load()
            if any(r["connection_id"] == connection.connection_id and r["account_id"] != owner for r in rows):
                raise PermissionError("Connection id belongs to another account")
            rows = [r for r in rows if r["connection_id"] != connection.connection_id]
            rows.append(connection.public())
            self._write(rows)
            return connection.public()

    def get(self, identity: dict, connection_id: str) -> dict | None:
        owner = verified_account_id(identity)
        with self._lock:
            return next((r.copy() for r in self._load()
                         if r["connection_id"] == connection_id and r["account_id"] == owner), None)
