import json
import pytest
from synapse_daemon.master_todo import snapshot, change


def test_backup_and_corrupt_primary_recovery(tmp_path):
    path = tmp_path / "tasks.json"
    snapshot(path)
    change(path, "complete", "001", event_id="first")
    assert path.with_suffix(".json.bak").exists()
    path.write_text("{corrupted", encoding="utf-8")
    recovered = snapshot(path)
    assert recovered["revision"] == 1
    assert len(recovered["tasks"]) == 3
    assert snapshot(path)["revision"] == 1


def test_event_id_must_match_operation(tmp_path):
    path = tmp_path / "tasks.json"
    change(path, "complete", "001", event_id="same", day="2026-10-08")
    with pytest.raises(ValueError, match="event id reused"):
        change(path, "complete", "002", event_id="same", day="2026-10-08")
