from pathlib import Path
from synapse_daemon.machine_fleet import ensure_machine_id, list_machines, upsert_local_machine
from synapse_daemon.storage import Storage

def _storage(tmp_path: Path):
    s=Storage(tmp_path/"data"); s.open(); s.migrate(); return s

def test_machine_id_is_stable(tmp_path: Path):
    data=tmp_path/"identity"
    assert ensure_machine_id(data)==ensure_machine_id(data)

def test_local_machine_registers_and_heartbeats_without_duplicates(tmp_path: Path):
    s=_storage(tmp_path); data=tmp_path/"identity"
    first=upsert_local_machine(s,data,"1.2.3","Justin Laptop")
    second=upsert_local_machine(s,data,"1.2.4","Justin Laptop")
    assert first["id"]==second["id"]
    rows=list_machines(s)
    assert len(rows)==1
    assert rows[0]["name"]=="Justin Laptop"
    assert rows[0]["synapse_version"]=="1.2.4"
    assert rows[0]["platform"] in {"windows","linux","darwin"}
    assert "daemon" in rows[0]["capabilities"]


def test_revoked_machine_cannot_heartbeat(tmp_path: Path):
    import pytest
    from synapse_daemon.errors import SynapseError

    storage=_storage(tmp_path); data=tmp_path/"identity"
    machine=upsert_local_machine(storage,data,"1.2.3")
    with storage.transaction() as conn:
        conn.execute("UPDATE synapse_machines SET revoked=1 WHERE id=?", (machine["id"],))
    with pytest.raises(SynapseError):
        upsert_local_machine(storage,data,"1.2.4")
    assert list_machines(storage)==[]
