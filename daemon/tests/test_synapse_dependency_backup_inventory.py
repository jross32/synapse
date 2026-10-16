"""Coverage for registered project backup inventory without reading secrets."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from synapse_dependency_backup_inventory import build_report


def test_registered_project_dedup_and_cloud_unverified(tmp_path):
    home=tmp_path/"owner"
    home.mkdir()
    root=home/"Synapse"
    root.mkdir()
    (root/"source.py").write_text("code")
    (root/"node_modules").mkdir()
    (root/"node_modules"/"rebuildable.bin").write_bytes(b"x"*500)
    registry=tmp_path/"registry.json"
    registry.write_text(json.dumps({"projects":[
        {"id":"synapse","path":str(root)},
        {"id":"duplicate","path":str(root)},
    ]}),encoding="utf8")
    result=build_report(registry,home)
    assert result["registered_projects"]==2
    assert result["unique_registered_paths"]==1
    assert result["available_paths"]==1
    assert result["registered_recovery_bytes_upper_bound"]==4
    assert all(row["remote_size_bytes"] is None for row in result["cloud_dependency_checklist"])
    assert all(row["remote_backup_verified"] is False for row in result["cloud_dependency_checklist"])


def test_missing_registered_path_is_reported_not_assumed(tmp_path):
    home=tmp_path/"home"
    home.mkdir()
    registry=tmp_path/"registry.json"
    registry.write_text(json.dumps({"projects":[{"id":"absent","path":str(tmp_path/"gone") }]}),encoding="utf8")
    result=build_report(registry,home)
    assert result["missing_paths"]==1
    assert result["registered_recovery_bytes_upper_bound"]==0
