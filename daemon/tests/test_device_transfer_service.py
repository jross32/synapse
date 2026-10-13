import pytest
from synapse_daemon.device_transfer_service import TransferService
from synapse_daemon.workspace_sync_core import checksum


def test_transfer_round_trip_using_relay_sized_packets(tmp_path):
    a = TransferService(tmp_path / "laptop")
    b = TransferService(tmp_path / "desktop")
    a_id, b_id = a.identity(), b.identity()
    a.authorize_peer(b_id["device_id"], b_id["public_key"])
    b.authorize_peer(a_id["device_id"], a_id["public_key"])
    project_a = tmp_path / "source"
    project_b = tmp_path / "destination"
    project_a.mkdir()
    project_b.mkdir()
    data = bytes(range(256)) * 500
    (project_a / "file.bin").write_bytes(data)
    manifest = a.begin_send("owner", "project", project_a, "file.bin", b_id["device_id"])
    assert manifest["chunk_count"] > 1
    assert b.receive_manifest("owner", manifest)["received"] == 0
    for index in range(manifest["chunk_count"]):
        item = a.packet("owner", manifest["transfer_id"], index)
        assert len(__import__("json").dumps(item)) < 131072
        b.receive_packet("owner", item["transfer_id"], item["index"], item["packet"])
    assert b.finalize("owner", manifest["transfer_id"], "project", project_b, None)["digest"] == checksum(data)
    assert (project_b / "file.bin").read_bytes() == data


def test_peer_binding_and_reuse_key_refusal(tmp_path):
    a = TransferService(tmp_path / "laptop")
    b = TransferService(tmp_path / "desktop")
    c = TransferService(tmp_path / "other")
    mine = a.identity()
    other = b.identity()
    assert a.authorize_peer(other["device_id"], other["public_key"])["authorized"]
    with pytest.raises(ValueError):
        a.authorize_peer(other["device_id"], c.identity()["public_key"])
    with pytest.raises(ValueError):
        a.authorize_peer(mine["device_id"], mine["public_key"])
    a.revoke_peer(other["device_id"])
    with pytest.raises(ValueError):
        a.begin_send("owner", "project", tmp_path, "file.bin", other["device_id"])
