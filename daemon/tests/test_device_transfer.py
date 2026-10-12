import pytest
from cryptography.hazmat.primitives.asymmetric import x25519

from synapse_daemon.device_transfer import (
    DeviceAuthorizationError, DeviceIdentity, DeviceTrustStore, open_envelope, seal,
)


def _pair(tmp_path):
    a = DeviceIdentity("laptop", x25519.X25519PrivateKey.generate())
    b = DeviceIdentity("desktop", x25519.X25519PrivateKey.generate())
    ta = DeviceTrustStore(tmp_path / "laptop-trust.json")
    tb = DeviceTrustStore(tmp_path / "desktop-trust.json")
    ta.authorize("desktop", b.public_key)
    tb.authorize("laptop", a.public_key)
    return a, b, ta, tb


def test_encrypted_roundtrip_and_project_binding(tmp_path):
    a, b, ta, tb = _pair(tmp_path)
    message = seal(a, "desktop", "app", "src/main.py", b"secret changes", ta)
    assert b"secret changes" not in str(message).encode()
    assert open_envelope(b, message, tb, expected_project="app") == ("src/main.py", b"secret changes")
    with pytest.raises(DeviceAuthorizationError):
        open_envelope(b, message, tb, expected_project="other")


def test_tamper_detected(tmp_path):
    a, b, ta, tb = _pair(tmp_path)
    message = seal(a, "desktop", "app", "src/main.py", b"secret", ta)
    message["path"] = "src/other.py"
    with pytest.raises(DeviceAuthorizationError):
        open_envelope(b, message, tb, expected_project="app")


def test_revoked_device_cannot_decrypt(tmp_path):
    a, b, ta, tb = _pair(tmp_path)
    message = seal(a, "desktop", "app", "src/main.py", b"secret", ta)
    tb.revoke("laptop")
    with pytest.raises(DeviceAuthorizationError):
        open_envelope(b, message, tb, expected_project="app")


def test_untrusted_recipient_cannot_be_sent_files(tmp_path):
    a, b, ta, tb = _pair(tmp_path)
    ta.revoke("desktop")
    with pytest.raises(DeviceAuthorizationError):
        seal(a, "desktop", "app", "src/main.py", b"secret", ta)


def test_simulated_laptop_desktop_file_roundtrip(tmp_path):
    from synapse_daemon.workspace_sync_core import atomic_write_verified, checksum
    laptop = tmp_path / "laptop"
    desktop = tmp_path / "desktop"
    laptop.mkdir()
    desktop.mkdir()
    (laptop / "main.py").write_bytes(b"v1 from laptop")
    a, b, ta, tb = _pair(tmp_path)
    envelope = seal(a, "desktop", "app", "main.py", (laptop / "main.py").read_bytes(), ta)
    path, payload = open_envelope(b, envelope, tb, expected_project="app")
    atomic_write_verified(desktop, path, payload, expected_digest=None, advertised_digest=checksum(payload))
    assert (desktop / "main.py").read_bytes() == (laptop / "main.py").read_bytes()
    (desktop / "main.py").write_bytes(b"v2 from desktop")
    reverse = seal(b, "laptop", "app", "main.py", (desktop / "main.py").read_bytes(), tb)
    path, payload = open_envelope(a, reverse, ta, expected_project="app")
    atomic_write_verified(laptop, path, payload, expected_digest=checksum(b"v1 from laptop"),
                          advertised_digest=checksum(payload))
    assert (laptop / "main.py").read_bytes() == b"v2 from desktop"
