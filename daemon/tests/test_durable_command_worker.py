"""End-to-end detached command verification."""
import subprocess
import sys
import time

from synapse_daemon.command_job_store import read_job
from synapse_daemon.durable_command_worker import launch


def wait_done(tmp_path, job_id, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        receipt = read_job(tmp_path, job_id)
        if receipt and receipt["status"] == "done":
            return receipt
        time.sleep(0.1)
    raise AssertionError(f"Job {job_id} never finished: {read_job(tmp_path, job_id)}")


def test_detached_command_receipt(tmp_path):
    job_id = "abcdef123456"
    result = launch(
        tmp_path, job_id,
        [sys.executable, "-c", "import time; time.sleep(1); print('durable-ok')"],
        str(tmp_path), timeout=15,
    )
    assert result["status"] == "starting"
    receipt = wait_done(tmp_path, job_id)
    assert receipt["result"]["ok"] is True
    assert "durable-ok" in receipt["result"]["stdout"]


def test_supervisor_survives_launcher_process_exit(tmp_path):
    """The process that calls launch exits before the command finishes."""
    job_id = "aabbccddeeff"
    script = (
        "import sys; "
        "from synapse_daemon.durable_command_worker import launch; "
        "launch(sys.argv[1], sys.argv[2], "
        "[sys.executable, '-c', "
        "'import time; time.sleep(2); print(\\\"survived-parent-exit\\\")'], "
        "sys.argv[1], 15)"
    )
    launcher = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), job_id],
        capture_output=True, text=True, timeout=15,
    )
    assert launcher.returncode == 0, launcher.stderr
    receipt = wait_done(tmp_path, job_id)
    assert receipt["result"]["ok"] is True, receipt
    assert "survived-parent-exit" in receipt["result"]["stdout"]
