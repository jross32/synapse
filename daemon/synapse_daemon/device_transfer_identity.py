"""Stable encrypted device transfer identity owned by one Synapse installation.

Keys never leave the local daemon. Account enrollment and remote peer trust
remain separate, explicit authorization steps.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from .device_transfer import DeviceIdentity
from .machine_fleet import ensure_machine_id
from .secrets import decrypt, encrypt

_FILE = "device-transfer-identity.json"


def load_or_create_device_identity(data_dir: Path) -> DeviceIdentity:
    data_dir = Path(data_dir)
    device_id = ensure_machine_id(data_dir)
    path = data_dir / _FILE
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("device_id") != device_id or value.get("version") != 1:
                raise ValueError("Device identity cannot be reused on a different machine")
            secret = base64.b64decode(value["encrypted_private_key"], validate=True)
            plain = decrypt(secret, data_dir=data_dir)
            private_bytes = base64.b64decode(plain.encode("ascii"), validate=True)
            if len(private_bytes) != 32:
                raise ValueError("Invalid device private key length")
            return DeviceIdentity(device_id, x25519.X25519PrivateKey.from_private_bytes(private_bytes))
        except (OSError, KeyError, TypeError, ValueError) as exc:
            # Fail closed: replacing an unreadable key would invalidate trust
            # and could silently orphan encrypted transfers.
            raise ValueError("Existing encrypted device identity cannot be opened") from exc
    private = x25519.X25519PrivateKey.generate()
    raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    encrypted = encrypt(base64.b64encode(raw).decode("ascii"), data_dir=data_dir)
    record = {"version": 1, "device_id": device_id,
              "encrypted_private_key": base64.b64encode(encrypted).decode("ascii")}
    data_dir.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="device-transfer-", suffix=".tmp", dir=data_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(record, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        # Atomically link the fully synced staging inode; a reader never sees
        # a partially written identity. Exclusive link also prevents a racing
        # launch from silently replacing an established private key.
        try:
            os.link(temporary, path)
        except FileExistsError:
            return load_or_create_device_identity(data_dir)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return DeviceIdentity(device_id, private)
