from synapse_daemon.command_job_store import read_job, save_job


def test_job_store_persists_result(tmp_path):
    record = {"status": "done", "exit_code": 0, "stdout": "finished"}
    save_job(tmp_path, "a1b2c3", record)
    assert read_job(tmp_path, "a1b2c3") == record


def test_job_store_rejects_traversal(tmp_path):
    assert read_job(tmp_path, "../anything") is None
    assert read_job(tmp_path, "x" * 5 + "/foo") is None


def test_job_store_replaces_atomically(tmp_path):
    save_job(tmp_path, "deadbeef", {"status": "running"})
    save_job(tmp_path, "deadbeef", {"status": "done", "exit_code": 1})
    assert read_job(tmp_path, "deadbeef")["exit_code"] == 1
