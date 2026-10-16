from pathlib import Path
import subprocess
import sys
import pytest
from synapse_daemon.chatgpt_commit_verification import verify_coding_receipt

def test_receipt_verifies_real_commit_and_tests(tmp_path):
    root=tmp_path
    def git(*args):
        return subprocess.run(["git",*args],cwd=root,check=True,capture_output=True,text=True)
    git("init")
    git("config","user.name","Synapse Tests")
    git("config","user.email","synapse-tests@example.invalid")
    (root/"daemon/tests").mkdir(parents=True)
    (root/"daemon/tests/test_example.py").write_text("def test_ok():\n    assert 2+2 == 4\n")
    git("add",".")
    git("commit","-m","test commit")
    commit=git("rev-parse","HEAD").stdout.strip()
    receipt=verify_coding_receipt(root,commit,["daemon/tests/test_example.py"],sys.executable)
    assert receipt["verified"] is True
    assert receipt["commit"]==commit
    assert receipt["changed_files"]==["daemon/tests/test_example.py"]
    (root/"dirty.txt").write_text("dirty")
    with pytest.raises(RuntimeError,match="not clean"):
        verify_coding_receipt(root,commit,["daemon/tests/test_example.py"],sys.executable)

def test_receipt_rejects_fake_commit_and_untrusted_paths(tmp_path):
    with pytest.raises(ValueError):
        verify_coding_receipt(tmp_path,"not-a-commit",["daemon/tests/test_x.py"],sys.executable)
    with pytest.raises(ValueError):
        verify_coding_receipt(tmp_path,"abc1234",["../../unsafe.py"],sys.executable)
