from pathlib import Path
import sqlite3,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from synapse_sqlite_snapshot_check import snapshot_check

def test_snapshot_check_never_modifies_db(tmp_path):
    db=tmp_path/"live.sqlite"
    con=sqlite3.connect(db)
    con.execute("CREATE TABLE items (name TEXT)")
    con.execute("INSERT INTO items VALUES ('a')")
    con.commit()
    con.close()
    original=db.read_bytes()
    result=snapshot_check(db)
    assert result["status"]=="validated_in_memory"
    assert result["disk_backup_created"] is False
    assert result["sqlite_quick_check"]=="ok"
    assert db.read_bytes()==original
