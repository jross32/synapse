"""Verified encrypted chunking, ordering and conflict-safe transfer promotion."""
import copy

import pytest
from cryptography.hazmat.primitives.asymmetric import x25519

from synapse_daemon.device_transfer import DeviceAuthorizationError, DeviceIdentity, DeviceTrustStore
from synapse_daemon.device_transfer_chunks import apply_received_transfer, make_packets, receive_packets
from synapse_daemon.workspace_sync_core import SyncConflict, checksum


@pytest.fixture
def peers(tmp_path):
    laptop = DeviceIdentity("laptop", x25519.X25519PrivateKey.generate())
    desktop = DeviceIdentity("desktop", x25519.X25519PrivateKey.generate())
    sender_trust = DeviceTrustStore(tmp_path / "laptop-trust.json")
    receiver_trust = DeviceTrustStore(tmp_path / "desktop-trust.json")
    sender_trust.authorize("desktop", desktop.public_key)
    receiver_trust.authorize("laptop", laptop.public_key)
    return laptop, desktop, sender_trust, receiver_trust


@pytest.mark.parametrize("payload", [b"", b"hello", b"sample" * 10_000], ids=["empty", "small", "large"])
def test_chunked_roundtrip_and_no_plaintext(peers, payload):
    a, b, at, bt = peers
    envelope = make_packets(a, "desktop", "proj", "src/main.py", payload, at, chunk_bytes=4096)
    assert receive_packets(b, envelope, bt, expected_project="proj") == ("src/main.py", payload)
    assert payload not in str(envelope).encode() if payload else True


def test_wrong_receiver_or_project_rejected(peers):
    a, b, at, bt = peers
    envelope = make_packets(a, "desktop", "proj", "src/main.py", b"x" * 9000, at, chunk_bytes=1024)
    with pytest.raises(DeviceAuthorizationError):
        receive_packets(b, envelope, bt, expected_project="other")
    c = DeviceIdentity("different", x25519.X25519PrivateKey.generate())
    with pytest.raises(DeviceAuthorizationError):
        receive_packets(c, envelope, bt, expected_project="proj")


@pytest.mark.parametrize("mutation", ["missing", "reverse", "duplicate", "digest", "path", "sender"])
def test_packet_mutation_rejected(peers, mutation):
    a, b, at, bt = peers
    envelope = make_packets(a, "desktop", "proj", "src/main.py", b"X" * 9000, at, chunk_bytes=2000)
    modified = copy.deepcopy(envelope)
    if mutation == "missing":
        modified["packets"].pop()
    elif mutation == "reverse":
        modified["packets"].reverse()
    elif mutation == "duplicate":
        modified["packets"][0] = modified["packets"][1]
    elif mutation == "digest":
        modified["digest"] = "0" * 64
    elif mutation == "path":
        modified["path"] = "src/other.py"
    else:
        modified["sender"] = "intruder"
    with pytest.raises(DeviceAuthorizationError):
        receive_packets(b, modified, bt, expected_project="proj")


def test_safe_atomic_promotion_and_conflict(peers, tmp_path):
    a, b, at, bt = peers
    target = tmp_path / "workspace"
    (target / "src").mkdir(parents=True)
    file = target / "src" / "main.py"
    file.write_bytes(b"old")
    envelope = make_packets(a, "desktop", "proj", "src/main.py", b"new" * 5000, at)
    with pytest.raises(SyncConflict):
        apply_received_transfer(target, b, envelope, bt, expected_project="proj",
                                expected_local_digest=checksum(b"wrong"))
    assert file.read_bytes() == b"old"
    result = apply_received_transfer(target, b, envelope, bt, expected_project="proj",
                                     expected_local_digest=checksum(b"old"))
    assert result == checksum(b"new" * 5000)
    assert file.read_bytes() == b"new" * 5000


def test_revocation_blocks_chunk_decryption(peers):
    a, b, at, bt = peers
    envelope = make_packets(a, "desktop", "proj", "file.txt", b"x", at)
    bt.revoke("laptop")
    with pytest.raises(DeviceAuthorizationError):
        receive_packets(b, envelope, bt, expected_project="proj")


def test_unsafe_path_and_oversize_rejected(peers):
    a, b, at, bt = peers
    with pytest.raises(ValueError):
        make_packets(a, "desktop", "proj", "../escape", b"a", at)
    with pytest.raises(ValueError):
        make_packets(a, "desktop", "proj", "main.py", b"a", at, chunk_bytes=262145)
