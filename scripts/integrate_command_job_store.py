"""Safe integration patch for persistent command metadata.

Run from Synapse repository root. Checks source anchors before changing anything.
"""
from pathlib import Path

path = Path("daemon/synapse_daemon/mcp_connector.py")
raw = path.read_text(encoding="utf-8-sig")
old = '''def _run_command_job_thread(job_id: str, shell_argv: list[str], cwd: str, timeout: float) -> None:'''
new = '''def _run_command_job_thread(job_id: str, shell_argv: list[str], cwd: str, timeout: float, data_dir: str | Path | None = None) -> None:'''
if raw.count(old) != 1:
    raise SystemExit("Function signature changed; refusing to patch")
raw = raw.replace(old, new, 1)
old = '''    job["result"] = result


def build_mcp_router('''
new = '''    job["result"] = result
    if data_dir is not None:
        from .command_job_store import save_job
        save_job(data_dir, job_id, {
            "status": "done", "cwd": cwd, "started_at": job["started_at"],
            "finished_at": job["finished_at"], "result": result,
        })


def build_mcp_router('''
if raw.count(old) != 1:
    raise SystemExit("Completion anchor changed; refusing to patch")
raw = raw.replace(old, new, 1)
old = '''                args=(job_id, shell_argv, cwd, timeout),'''
new = '''                args=(job_id, shell_argv, cwd, timeout, storage.data_dir),'''
if raw.count(old) != 1:
    raise SystemExit("Job start anchor changed; refusing to patch")
raw = raw.replace(old, new, 1)
old = '''            job = _command_jobs.get(job_id)
            if job is None:
                raise ValueError(
                    f"Unknown job_id: {job_id!r}'''
new = '''            job = _command_jobs.get(job_id)
            if job is None:
                from .command_job_store import read_job
                recovered = read_job(storage.data_dir, job_id)
                if recovered is not None:
                    return {"job_id": job_id, **recovered}
                raise ValueError(
                    f"Unknown job_id: {job_id!r}'''
if raw.count(old) != 1:
    raise SystemExit("Job lookup anchor changed; refusing to patch")
raw = raw.replace(old, new, 1)
path.write_text(raw, encoding="utf-8")
print("INTEGRATED")
