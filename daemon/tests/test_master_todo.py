import pytest
from synapse_daemon.master_todo import snapshot, change


def test_seed_and_daily_recurrence(tmp_path):
    path = tmp_path / "master.json"
    first = snapshot(path, "2026-10-08")
    assert [x["id"] for x in first["tasks"]] == ["001", "002", "daily-review"]
    done = change(path, "complete", "daily-review", day="2026-10-08", expected_revision=1, event_id="evt-1")
    assert done["tasks"][2]["done_today"] is True
    assert snapshot(path, "2026-10-09")["tasks"][2]["done_today"] is False
    assert change(path, "complete", "daily-review", day="2026-10-08", event_id="evt-1")["revision"] == 2
    with pytest.raises(ValueError, match="revision conflict"):
        change(path, "complete", "001", expected_revision=1)
    assert change(path, "complete", "001")["tasks"][0]["done_today"] is True
    assert change(path, "reopen", "daily-review", day="2026-10-08")["tasks"][2]["done_today"] is False


def test_add_and_errors(tmp_path):
    path = tmp_path / "data.json"
    added = change(path, "add", "new-id", title="Sell one item")
    assert added["tasks"][-1]["title"] == "Sell one item"
    with pytest.raises(ValueError, match="duplicate"):
        change(path, "add", "new-id", title="Again")
    with pytest.raises(KeyError):
        change(path, "complete", "missing")
