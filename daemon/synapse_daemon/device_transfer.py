"""Authenticated, end-to-end encrypted workspace payload envelopes.

Device trust must be established via an independently authenticated channel;
this module never silently enrolls a remote device.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .workspace_sync_core import checksum, safe_relative_path


class DeviceAuthorizationError(ValueError):
    pass


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    private_key: x25519.X25519PrivateKey

    @property
    def public_key(self) -> bytes:
        return self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )


class DeviceTrustStore:
    """Local trust registry: only explicitly enrolled, non-revoked peers may transfer."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "devices": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def authorize(self, device_id: str, public_key: bytes) -> None:
        if not device_id or len(public_key) != 32:
            raise DeviceAuthorizationError("Invalid device identity")
        state = self._read()
        state["devices"][device_id] = {"public_key": base64.b64encode(public_key).decode(), "revoked": False}
        self._write(state)

    def revoke(self, device_id: str) -> None:
        state = self._read()
        if device_id not in state["devices"]:
            raise DeviceAuthorizationError("Unknown device")
        state["devices"][device_id]["revoked"] = True
        self._write(state)

    def require(self, device_id: str) -> bytes:
        item = self._read()["devices"].get(device_id)
        if not item or item.get("revoked"):
            raise DeviceAuthorizationError("Device not authorized")
        return base64.b64decode(item["public_key"], validate=True)

    def _write(self, state: dict) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)


def _key(private: x25519.X25519PrivateKey, peer_public: bytes, salt: bytes) -> bytes:
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(peer_public))
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt,
                info=b"synapse-workspace-transfer-v1").derive(shared)


def _metadata(sender: str, recipient: str, project: str, relative: str, digest: str) -> bytes:
    return json.dumps({"sender": sender, "recipient": recipient, "project": project,
                       "path": safe_relative_path(relative), "digest": digest},
                      sort_keys=True, separators=(",", ":")).encode()


def seal(sender: DeviceIdentity, recipient_id: str, project_id: str, relative: str,
         payload: bytes, trust: DeviceTrustStore) -> dict:
    recipient_key = trust.require(recipient_id)
    digest = checksum(payload)
    aad = _metadata(sender.device_id, recipient_id, project_id, relative, digest)
    salt, nonce = os.urandom(16), os.urandom(12)
    ciphertext = AESGCM(_key(sender.private_key, recipient_key, salt)).encrypt(nonce, payload, aad)
    return {"version": 1, "sender": sender.device_id, "recipient": recipient_id,
            "project": project_id, "path": safe_relative_path(relative), "digest": digest,
            "salt": base64.b64encode(salt).decode(), "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode()}


def open_envelope(receiver: DeviceIdentity, envelope: dict, trust: DeviceTrustStore,
                  *, expected_project: str) -> tuple[str, bytes]:
    if envelope.get("version") != 1 or envelope.get("recipient") != receiver.device_id:
        raise DeviceAuthorizationError("Wrong recipient or protocol")
    if envelope.get("project") != expected_project:
        raise DeviceAuthorizationError("Project authorization mismatch")
    sender_id = envelope["sender"]
    sender_key = trust.require(sender_id)
    relative = safe_relative_path(envelope["path"])
    aad = _metadata(sender_id, receiver.device_id, expected_project, relative, envelope["digest"])
    try:
        salt = base64.b64decode(envelope["salt"], validate=True)
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
        if len(salt) != 16 or len(nonce) != 12:
            raise DeviceAuthorizationError("Malformed encryption parameters")
        payload = AESGCM(_key(receiver.private_key, sender_key, salt)).decrypt(nonce, ciphertext, aad)
    except (InvalidTag, ValueError) as exc:
        raise DeviceAuthorizationError("Encrypted transfer failed verification") from exc
    if checksum(payload) != envelope["digest"]:
        raise DeviceAuthorizationError("Content digest mismatch")
    return relative, payload
