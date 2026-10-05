import json
import os
import subprocess
import sys
from pathlib import Path

import async_controller as ac


class DummyProc:
    pid = 4242


def test_worker_python_prefers_repo_venv():
    p = ac.worker_python()
    assert p.exists()
    assert ".venv" in str(p)


def test_submit_writes_durable_status(monkeypatch, tmp_path):
    data = tmp_path / "data"
    latest = data / "latest.json"
    monkeypatch.setattr(ac, "DATA_ROOT", data)
    monkeypatch.setattr(ac, "LATEST", latest)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: DummyProc())
    state = ac.submit("in.jpg", "out.jpg", "warm-gallery", "u2netp")
    assert state["status"] == "starting"
    assert state["worker_pid"] == 4242
    saved = json.loads(Path(state["status_file"]).read_text())
    assert saved["output"] == "out.jpg"
    assert ac.status()["run_id"] == state["run_id"]


def test_submit_batch_writes_kind_and_paths(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setattr(ac, "DATA_ROOT", data)
    monkeypatch.setattr(ac, "LATEST", data / "latest.json")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: DummyProc())
    state = ac.submit_batch("in", "out", "clean-white", "u2netp")
    assert state["kind"] == "batch"
    assert state["input_dir"] == "in"
    assert state["output_dir"] == "out"


def test_status_none_when_no_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(ac, "LATEST", tmp_path / "missing.json")
    assert ac.status()["status"] == "none"


def test_async_worker_error_is_recorded(monkeypatch, tmp_path):
    # Exercise the worker error-state contract in-process. Spawning a fresh
    # Python process imports ONNX Runtime and can make this unit test take
    # tens of seconds even though no inference is performed.
    import async_worker as worker
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"status": "queued"}), encoding="utf-8")
    monkeypatch.setattr(worker, "process", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("missing.jpg")))
    monkeypatch.setattr(sys, "argv", [
        "async_worker.py", "--status", str(status), "--input", str(tmp_path/"missing.jpg"),
        "--output", str(tmp_path/"out.jpg"),
    ])
    try:
        worker.main()
    except FileNotFoundError:
        pass
    saved = json.loads(status.read_text())
    assert saved["status"] == "error"
    assert "failed" in saved["message"].lower()