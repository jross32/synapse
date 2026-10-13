"""Persistent encrypted transfer inbox; transport authorization is external."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from .device_transfer import DeviceAuthorizationError, DeviceIdentity, DeviceTrustStore, open_envelope
from .device_transfer_chunks import receive_packets, MAX_CHUNK_BYTES, MAX_TRANSFER_BYTES
from .workspace_sync_core import safe_relative_path, atomic_write_verified


class InboxConflict(ValueError):
    pass


class TransferInbox:
    def __init__(self, database: Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS transfers (
              account TEXT NOT NULL, transfer_id TEXT NOT NULL, manifest TEXT NOT NULL,
              PRIMARY KEY(account, transfer_id));
            CREATE TABLE IF NOT EXISTS packets (
              account TEXT NOT NULL, transfer_id TEXT NOT NULL, part INTEGER NOT NULL,
              packet TEXT NOT NULL, PRIMARY KEY(account,transfer_id,part));
            """)

    def _connect(self):
        return sqlite3.connect(self.database, timeout=15)

    def register(self, account: str, transfer: dict) -> None:
        if not account or not isinstance(transfer, dict):
            raise InboxConflict("Authenticated account and manifest required")
        manifest = {k: v for k, v in transfer.items() if k != "packets"}
        token = manifest.get("transfer_id")
        count = manifest.get("chunk_count")
        size = manifest.get("size")
        if not isinstance(token, str) or len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
            raise InboxConflict("Invalid transfer ID")
        if not isinstance(count, int) or not 1 <= count <= (MAX_TRANSFER_BYTES + MAX_CHUNK_BYTES - 1) // MAX_CHUNK_BYTES + 1:
            raise InboxConflict("Invalid transfer chunk count")
        if not isinstance(size, int) or not 0 <= size <= MAX_TRANSFER_BYTES:
            raise InboxConflict("Invalid transfer size")
        if not all(isinstance(manifest.get(k), str) and manifest[k] for k in
                   ("sender", "recipient", "project", "digest", "path")):
            raise InboxConflict("Incomplete transfer manifest")
        safe_relative_path(manifest["path"])
        if len(manifest["digest"]) != 64:
            raise InboxConflict("Invalid digest")
        serialized = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        with self._connect() as db:
            row = db.execute("SELECT manifest FROM transfers WHERE account=? AND transfer_id=?",
                             (account, token)).fetchone()
            if row and row[0] != serialized:
                raise InboxConflict("Transfer identity reused with changed metadata")
            db.execute("INSERT OR IGNORE INTO transfers(account,transfer_id,manifest) VALUES(?,?,?)",
                       (account, token, serialized))

    def accept(self, account: str, transfer_id: str, index: int, packet: dict,
               receiver: DeviceIdentity, trust: DeviceTrustStore) -> int:
        with self._connect() as db:
            row = db.execute("SELECT manifest FROM transfers WHERE account=? AND transfer_id=?",
                             (account, transfer_id)).fetchone()
            if not row:
                raise InboxConflict("Unknown or unauthorized transfer")
            manifest = json.loads(row[0])
            if not isinstance(index, int) or not 0 <= index < manifest["chunk_count"]:
                raise InboxConflict("Invalid chunk index")
            if not isinstance(packet, dict) or packet.get("sender") != manifest["sender"]:
                raise InboxConflict("Sender mismatch")
            if manifest["recipient"] != receiver.device_id:
                raise InboxConflict("Wrong recipient")
            part, content = open_envelope(receiver, packet, trust, expected_project=manifest["project"])
            expected = f'{manifest["path"]}.synapse-chunks/{transfer_id}/{index:06d}'
            if part != expected or len(content) > MAX_CHUNK_BYTES:
                raise InboxConflict("Chunk path or size mismatch")
            serialized = json.dumps(packet, sort_keys=True, separators=(",", ":"))
            previous = db.execute(
                "SELECT packet FROM packets WHERE account=? AND transfer_id=? AND part=?",
                (account, transfer_id, index)).fetchone()
            if previous and previous[0] != serialized:
                raise InboxConflict("Conflicting duplicate packet")
            db.execute("INSERT OR IGNORE INTO packets(account,transfer_id,part,packet) VALUES(?,?,?,?)",
                       (account, transfer_id, index, serialized))
            return db.execute("SELECT count(*) FROM packets WHERE account=? AND transfer_id=?",
                              (account, transfer_id)).fetchone()[0]

    def progress(self, account: str, transfer_id: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT manifest FROM transfers WHERE account=? AND transfer_id=?",
                             (account, transfer_id)).fetchone()
            if row is None:
                raise InboxConflict("Unknown transfer")
            count = db.execute("SELECT count(*) FROM packets WHERE account=? AND transfer_id=?",
                               (account, transfer_id)).fetchone()[0]
            return {"received": count, "total": json.loads(row[0])["chunk_count"], "complete": count == json.loads(row[0])["chunk_count"]}

    def finish(self, account: str, transfer_id: str, root: Path,
               receiver: DeviceIdentity, trust: DeviceTrustStore,
               *, expected_project: str, expected_local_digest: str | None) -> str:
        with self._connect() as db:
            row = db.execute("SELECT manifest FROM transfers WHERE account=? AND transfer_id=?",
                             (account, transfer_id)).fetchone()
            if not row:
                raise InboxConflict("Unknown transfer")
            manifest = json.loads(row[0])
            if manifest["project"] != expected_project or manifest["recipient"] != receiver.device_id:
                raise InboxConflict("Destination project mismatch")
            parts = db.execute("SELECT part,packet FROM packets WHERE account=? AND transfer_id=? ORDER BY part",
                               (account, transfer_id)).fetchall()
            if len(parts) != manifest["chunk_count"] or any(i != p[0] for i,p in enumerate(parts)):
                raise InboxConflict("Transfer incomplete")
            transfer = dict(manifest, packets=[json.loads(row[1]) for row in parts])
            relative, payload = receive_packets(receiver, transfer, trust, expected_project=expected_project)
            result = atomic_write_verified(root, relative, payload,
                                           expected_digest=expected_local_digest,
                                           advertised_digest=manifest["digest"])
            db.execute("DELETE FROM packets WHERE account=? AND transfer_id=?", (account, transfer_id))
            db.execute("DELETE FROM transfers WHERE account=? AND transfer_id=?", (account, transfer_id))
            return result
