from pathlib import Path
import sqlite3,sys
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from synapse_restore_verify import make_test_bundle,validate_and_restore,checked_relative

def test_isolated_sqlite_restore(tmp_path):
    db=tmp_path/"test.sqlite"
    c=sqlite3.connect(db)
    c.execute("CREATE TABLE items (v TEXT)")
    c.execute("INSERT INTO items VALUES ('preserved')")
    c.commit();c.close()
    bundle=make_test_bundle({"data/test.sqlite":db.read_bytes(),"settings/config.json":b'{"ok":true}'},tmp_path/"test.zip")
    target=tmp_path/"restored"
    assert validate_and_restore(bundle,target)["restored"] is False
    assert not target.exists()
    assert validate_and_restore(bundle,target,apply=True)["files_verified"]==2
    c=sqlite3.connect(target/"data"/"test.sqlite")
    assert c.execute("select v from items").fetchone()[0]=="preserved"
    c.close()
    with pytest.raises(FileExistsError):validate_and_restore(bundle,target,apply=True)

@pytest.mark.parametrize("bad",["../secret.txt","/etc/passwd","C:/Windows/a","a\\evil","."])
def test_rejects_traversal(bad):
    with pytest.raises(ValueError):checked_relative(bad)

def test_detects_corrupt_bundle(tmp_path):
    bundle=make_test_bundle({"file.txt":b"untampered"},tmp_path/"test.zip")
    import zipfile,json
    corrupt=tmp_path/"corrupt.zip"
    with zipfile.ZipFile(bundle) as z,zipfile.ZipFile(corrupt,"w") as out:
        for name in z.namelist():
            out.writestr(name,b"changed" if name=="payload/file.txt" else z.read(name))
    with pytest.raises(ValueError):validate_and_restore(corrupt,tmp_path/"restored")

