from pathlib import Path
import sqlite3
import sys
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from synapse_sqlite_backup_verify import verified_sqlite_backup

def test_online_sqlite_backup_and_isolated_restore(tmp_path):
    source=tmp_path/"live.db"
    with sqlite3.connect(source) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE records(id INTEGER PRIMARY KEY, message TEXT)")
        conn.execute("INSERT INTO records(message) VALUES ('synthetic-account-fixture')")
        conn.commit()
        record=verified_sqlite_backup(source,tmp_path/"backup.db",tmp_path/"restored.db")
        assert record["status"]=="SQLITE_RESTORE_VERIFIED"
        assert record["archive_sha256"]==record["restore_sha256"]
        assert record["source_preserved"] is True
        with sqlite3.connect(tmp_path/"restored.db") as check:
            assert check.execute("SELECT message FROM records").fetchone()[0]=="synthetic-account-fixture"
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1

def test_never_overwrites_archive_or_source(tmp_path):
    source=tmp_path/"live.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE t(n INTEGER)")
        conn.commit()
    with pytest.raises(ValueError):
        verified_sqlite_backup(source,source,tmp_path/"new.db")
    archive=tmp_path/"existing.db"
    archive.write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        verified_sqlite_backup(source,archive,tmp_path/"new.db")
    assert archive.read_bytes()==b"preserve"

def test_rejects_missing_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        verified_sqlite_backup(tmp_path/"missing.db",tmp_path/"backup.db",tmp_path/"restore.db")

