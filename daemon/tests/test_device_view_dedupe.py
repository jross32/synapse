from pathlib import Path

from synapse_daemon.profile import ProfileManager
from synapse_daemon.storage import Storage


def test_duplicate_historical_ids_display_once(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    manager = ProfileManager(storage)
    current = manager.ensure_current_host()
    with storage.transaction() as conn:
        conn.execute(
            "INSERT INTO profile_hosts (id,name,platform,current_host,last_seen_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            ("legacy-machine-id", current.name, current.platform, 0,
             current.last_seen_at, current.created_at, current.updated_at),
        )
    hosts = manager.list_hosts()
    assert len(hosts) == 1
    assert hosts[0].id == current.id
    assert storage.conn.execute("SELECT COUNT(*) FROM profile_hosts").fetchone()[0] == 2
