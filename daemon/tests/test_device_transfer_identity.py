import base64
import json
import pytest
from synapse_daemon.device_transfer_identity import load_or_create_device_identity
from synapse_daemon.machine_fleet import ensure_machine_id


def test_identity_survives_restart_and_stays_encrypted(tmp_path):
    first = load_or_create_device_identity(tmp_path)
    again = load_or_create_device_identity(tmp_path)
    assert first.device_id == ensure_machine_id(tmp_path)
    assert first.public_key == again.public_key
    stored = (tmp_path / "device-transfer-identity.json").read_text(encoding="utf-8")
    assert base64.b64encode(first.private_key.private_bytes_raw()).decode("ascii") not in stored
    assert "encrypted_private_key" in json.loads(stored)


def test_corrupt_identity_fails_closed_without_replacement(tmp_path):
    original = load_or_create_device_identity(tmp_path)
    path = tmp_path / "device-transfer-identity.json"
    data = json.loads(path.read_text())
    data["encrypted_private_key"] = "invalid"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="cannot be opened"):
        load_or_create_device_identity(tmp_path)
    assert original.device_id == ensure_machine_id(tmp_path)


def test_identity_must_match_its_machine_id(tmp_path):
    load_or_create_device_identity(tmp_path)
    (tmp_path / "machine-id").write_text("different-machine")
    with pytest.raises(ValueError, match="cannot be opened"):
        load_or_create_device_identity(tmp_path)
