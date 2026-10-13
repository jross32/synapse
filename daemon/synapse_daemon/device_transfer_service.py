"""Persistent encrypted file-transfer operations for per-device MCP dispatch."""
from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .device_transfer import DeviceTrustStore
from .device_transfer_chunks import make_packets
from .device_transfer_identity import load_or_create_device_identity
from .device_transfer_inbox import TransferInbox
from .workspace_sync_core import safe_relative_path

RELAY_CHUNK_BYTES = 32 * 1024


class TransferService:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.trust = DeviceTrustStore(self.data_dir / "device-transfer-trust.json")
        self.inbox = TransferInbox(self.data_dir / "device-transfer-inbox.sqlite")
        self.outbox = self.data_dir / "device-transfer-outbox"
        self.outbox.mkdir(parents=True, exist_ok=True)

    def identity(self) -> dict[str, str]:
        me = load_or_create_device_identity(self.data_dir)
        return {"device_id": me.device_id,
                "public_key": base64.b64encode(me.public_key).decode("ascii")}

    def authorize_peer(self, peer_id: str, public_key: str) -> dict:
        me = load_or_create_device_identity(self.data_dir)
        if not peer_id or peer_id == me.device_id:
            raise ValueError("Invalid peer device")
        decoded = base64.b64decode(public_key, validate=True)
        if len(decoded) != 32:
            raise ValueError("Expected 32-byte X25519 public key")
        try:
            prior = self.trust.require(peer_id)
        except ValueError:
            prior = None
        if prior is not None and prior != decoded:
            raise ValueError("Peer key changed: revoke and reauthorize explicitly")
        self.trust.authorize(peer_id, decoded)
        return {"authorized": True, "device_id": peer_id}

    def revoke_peer(self, peer_id: str) -> dict:
        self.trust.revoke(peer_id)
        return {"revoked": True, "device_id": peer_id}

    @staticmethod
    def _file_in_project(root: Path, relative: str) -> Path:
        safe_relative_path(relative)
        base = Path(root).resolve(strict=True)
        candidate = base / relative
        current = candidate
        while current != base:
            if current.is_symlink():
                raise ValueError("Symlinks are not valid transfer sources")
            current = current.parent
        file = candidate.resolve(strict=False)
        if not file.is_relative_to(base):
            raise ValueError("Path escapes project root")
        return file

    def begin_send(self, account_id: str, project_id: str, project_root: Path,
                   relative_path: str, recipient_id: str) -> dict:
        sender = load_or_create_device_identity(self.data_dir)
        file = self._file_in_project(project_root, relative_path)
        if not file.is_file():
            raise ValueError("Source file not found")
        if file.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("File exceeds transfer limit")
        transfer = make_packets(sender, recipient_id, project_id,
                                relative_path, file.read_bytes(), self.trust,
                                chunk_bytes=RELAY_CHUNK_BYTES)
        manifest = {k: v for k, v in transfer.items() if k != "packets"}
        record = {"account_id": account_id, "transfer": transfer}
        name = self.outbox / (manifest["transfer_id"] + ".json")
        fd, temp = tempfile.mkstemp(prefix="transfer-", suffix=".tmp", dir=self.outbox)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(record, output, separators=(",", ":"))
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp, name)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return manifest

    def packet(self, account_id: str, transfer_id: str, index: int) -> dict:
        if len(transfer_id) != 32 or any(c not in "0123456789abcdef" for c in transfer_id):
            raise ValueError("Invalid transfer ID")
        record = json.loads((self.outbox / (transfer_id + ".json")).read_text(encoding="utf-8"))
        if record["account_id"] != account_id:
            raise ValueError("Transfer not owned by this account")
        packets = record["transfer"]["packets"]
        if not isinstance(index, int) or not 0 <= index < len(packets):
            raise ValueError("Chunk index out of range")
        return {"transfer_id": transfer_id, "index": index, "packet": packets[index]}

    def receive_manifest(self, account_id: str, manifest: dict) -> dict:
        identity = load_or_create_device_identity(self.data_dir)
        if manifest.get("recipient") != identity.device_id:
            raise ValueError("Transfer destination does not match this device")
        self.trust.require(manifest["sender"])
        self.inbox.register(account_id, manifest)
        return self.inbox.progress(account_id, manifest["transfer_id"])

    def receive_packet(self, account_id: str, transfer_id: str,
                       index: int, packet: dict) -> dict:
        me = load_or_create_device_identity(self.data_dir)
        self.inbox.accept(account_id, transfer_id, index, packet, me, self.trust)
        return self.inbox.progress(account_id, transfer_id)

    def finalize(self, account_id: str, transfer_id: str,
                 project_id: str, project_root: Path,
                 expected_local_digest: str | None) -> dict:
        me = load_or_create_device_identity(self.data_dir)
        digest = self.inbox.finish(account_id, transfer_id, Path(project_root), me,
                                   self.trust, expected_project=project_id,
                                   expected_local_digest=expected_local_digest)
        return {"complete": True, "digest": digest, "transfer_id": transfer_id}
