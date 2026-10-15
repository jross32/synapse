from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from synapse_backup_inventory import measure,git_info

def test_generated_folders_excluded_from_recovery_estimate(tmp_path):
    root=tmp_path/"project"
    root.mkdir()
    (root/"source.py").write_bytes(b"important")
    (root/"node_modules").mkdir()
    (root/"node_modules"/"package.dat").write_bytes(b"x"*100)
    (root/".venv").mkdir()
    (root/".venv"/"python.exe").write_bytes(b"x"*200)
    metrics=measure(root)
    assert metrics["total_bytes"]==309
    assert metrics["recovery_bytes_upper_bound"]==9
    assert metrics["generated_bytes"]==300

def test_git_probe_no_source_mutations(tmp_path):
    root=tmp_path/"project"
    root.mkdir()
    assert git_info(root)=={"git":False}
