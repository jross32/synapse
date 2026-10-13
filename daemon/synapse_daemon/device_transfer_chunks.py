"""Bounded authenticated chunk envelopes for two trusted Synapse devices.

No transport, identity enrollment, or automatic file deployment happens here.
The caller supplies the approved peers and uses an authenticated relay to
deliver packets. An authorized receiver may assemble only an entire verified
transfer, then perform a conflict-safe write to its own project root.
"""
from __future__ import annotations

import secrets
from pathlib import Path

from .device_transfer import DeviceAuthorizationError, DeviceIdentity, DeviceTrustStore, open_envelope, seal
from .workspace_sync_core import atomic_write_verified, checksum, safe_relative_path

MAX_TRANSFER_BYTES = 64 * 1024 * 1024
MAX_CHUNK_BYTES = 256 * 1024


def make_packets(
    sender: DeviceIdentity,
    recipient_id: str,
    project_id: str,
    relative_path: str,
    data: bytes,
    trust: DeviceTrustStore,
    *,
    chunk_bytes: int = MAX_CHUNK_BYTES,
) -> dict:
    relative_path = safe_relative_path(relative_path)
    if not project_id or not recipient_id or len(data) > MAX_TRANSFER_BYTES:
        raise ValueError("Invalid transfer or payload too large")
    if not 1 <= chunk_bytes <= MAX_CHUNK_BYTES:
        raise ValueError("Invalid chunk size")
    transfer_id = secrets.token_hex(16)
    chunks = [data[i:i + chunk_bytes] for i in range(0, len(data), chunk_bytes)] or [b""]
    packets = [
        seal(sender, recipient_id, project_id,
             f"{relative_path}.synapse-chunks/{transfer_id}/{index:06d}",
             chunk, trust)
        for index, chunk in enumerate(chunks)
    ]
    return {
        "version": 1, "transfer_id": transfer_id,
        "sender": sender.device_id, "recipient": recipient_id,
        "project": project_id, "path": relative_path,
        "digest": checksum(data), "size": len(data),
        "chunk_count": len(packets), "packets": packets,
    }


def receive_packets(
    receiver: DeviceIdentity,
    transfer: dict,
    trust: DeviceTrustStore,
    *,
    expected_project: str,
) -> tuple[str, bytes]:
    if not isinstance(transfer, dict) or transfer.get("version") != 1:
        raise DeviceAuthorizationError("Invalid transfer protocol")
    if transfer.get("recipient") != receiver.device_id or transfer.get("project") != expected_project:
        raise DeviceAuthorizationError("Transfer destination or project mismatch")
    relative = safe_relative_path(transfer["path"])
    transfer_id = transfer.get("transfer_id")
    count = transfer.get("chunk_count")
    size = transfer.get("size")
    if not isinstance(transfer_id, str) or len(transfer_id) != 32 or any(c not in "0123456789abcdef" for c in transfer_id):
        raise DeviceAuthorizationError("Invalid transfer identity")
    if not isinstance(count, int) or not 1 <= count <= (MAX_TRANSFER_BYTES + MAX_CHUNK_BYTES - 1) // MAX_CHUNK_BYTES + 1:
        raise DeviceAuthorizationError("Invalid chunk count")
    if not isinstance(size, int) or not 0 <= size <= MAX_TRANSFER_BYTES:
        raise DeviceAuthorizationError("Invalid transfer size")
    packets = transfer.get("packets")
    if not isinstance(packets, list) or len(packets) != count:
        raise DeviceAuthorizationError("Missing or duplicated transfer packets")
    result = bytearray()
    for index, packet in enumerate(packets):
        if not isinstance(packet, dict) or packet.get("sender") != transfer.get("sender"):
            raise DeviceAuthorizationError("Transfer sender mismatch")
        expected_part = f"{relative}.synapse-chunks/{transfer_id}/{index:06d}"
        part_path, data = open_envelope(receiver, packet, trust, expected_project=expected_project)
        if part_path != expected_part or len(data) > MAX_CHUNK_BYTES:
            raise DeviceAuthorizationError("Chunk order, path, or size invalid")
        result.extend(data)
        if len(result) > size:
            raise DeviceAuthorizationError("Transfer exceeds advertised size")
    if len(result) != size or checksum(result) != transfer.get("digest"):
        raise DeviceAuthorizationError("Transfer integrity verification failed")
    return relative, bytes(result)


def apply_received_transfer(
    root: Path,
    receiver: DeviceIdentity,
    transfer: dict,
    trust: DeviceTrustStore,
    *,
    expected_project: str,
    expected_local_digest: str | None,
) -> str:
    relative, payload = receive_packets(receiver, transfer, trust, expected_project=expected_project)
    return atomic_write_verified(root, relative, payload,
                                 expected_digest=expected_local_digest,
                                 advertised_digest=transfer["digest"])
