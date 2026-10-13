from cryptography.hazmat.primitives.asymmetric import x25519
import pytest
from synapse_daemon.device_transfer import DeviceIdentity, DeviceTrustStore
from synapse_daemon.device_transfer_chunks import make_packets
from synapse_daemon.device_transfer_inbox import TransferInbox, InboxConflict


def test_resume_and_commit_verified_transfer(tmp_path):
    laptop = DeviceIdentity("laptop", x25519.X25519PrivateKey.generate())
    desktop = DeviceIdentity("desktop", x25519.X25519PrivateKey.generate())
    lt = DeviceTrustStore(tmp_path / "lt.json")
    dt = DeviceTrustStore(tmp_path / "dt.json")
    lt.authorize("desktop", desktop.public_key)
    dt.authorize("laptop", laptop.public_key)
    payload = b"verified transfer" * 1000
    transfer = make_packets(laptop, "desktop", "project", "main.txt", payload, lt, chunk_bytes=1024)
    inbox_path = tmp_path / "inbox.sqlite"
    inbox = TransferInbox(inbox_path)
    inbox.register("account-a", transfer)
    inbox.accept("account-a", transfer["transfer_id"], 0, transfer["packets"][0], desktop, dt)
    assert inbox.progress("account-a", transfer["transfer_id"])["received"] == 1
    inbox = TransferInbox(inbox_path)
    assert inbox.progress("account-a", transfer["transfer_id"])["received"] == 1
    with pytest.raises(InboxConflict):
        inbox.finish("account-a", transfer["transfer_id"], tmp_path, desktop, dt,
                     expected_project="project", expected_local_digest=None)
    with pytest.raises(InboxConflict):
        inbox.progress("account-b", transfer["transfer_id"])
    for i, part in enumerate(transfer["packets"]):
        inbox.accept("account-a", transfer["transfer_id"], i, part, desktop, dt)
    assert inbox.progress("account-a", transfer["transfer_id"])["complete"]
    assert inbox.finish("account-a", transfer["transfer_id"], tmp_path, desktop, dt,
                        expected_project="project", expected_local_digest=None) == transfer["digest"]
    assert (tmp_path / "main.txt").read_bytes() == payload
    with pytest.raises(InboxConflict):
        inbox.progress("account-a", transfer["transfer_id"])


def test_conflicting_duplicate_and_reused_transfer_id(tmp_path):
    a = DeviceIdentity("a", x25519.X25519PrivateKey.generate())
    b = DeviceIdentity("b", x25519.X25519PrivateKey.generate())
    at = DeviceTrustStore(tmp_path / "at.json")
    bt = DeviceTrustStore(tmp_path / "bt.json")
    at.authorize("b", b.public_key)
    bt.authorize("a", a.public_key)
    t = make_packets(a, "b", "p", "file", b"x"*1500, at, chunk_bytes=1000)
    inbox = TransferInbox(tmp_path / "inbox.sqlite")
    inbox.register("tenant", t)
    inbox.accept("tenant", t["transfer_id"], 0, t["packets"][0], b, bt)
    with pytest.raises(InboxConflict):
        inbox.accept("tenant", t["transfer_id"], 0, t["packets"][1], b, bt)
    changed = dict(t, digest="0"*64)
    with pytest.raises(InboxConflict):
        inbox.register("tenant", changed)
