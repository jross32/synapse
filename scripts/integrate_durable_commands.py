"""One-time narrow source transformation for the existing async command endpoint."""
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "daemon" / "synapse_daemon" / "mcp_connector.py"
source = path.read_text(encoding="utf-8")
start = source.index('            job_id = uuid.uuid4().hex[:12]\n', source.index('if name == "synapse_run_command_async":'))
end = source.index('\n        if name == "synapse_get_command_result":', start)
old = source[start:end]
if "target=_run_command_job_thread" not in old:
    raise SystemExit("Unexpected async handler; refusing to modify")
new = '''            job_id = uuid.uuid4().hex[:12]
            from .durable_command_worker import launch as launch_durable_command
            launched = launch_durable_command(storage.data_dir, job_id, shell_argv, cwd, timeout)
            return {
                "job_id": job_id,
                "status": launched["status"],
                "note": "Detached supervisor owns this job. Poll synapse_get_command_result; "
                        "completion receipts persist across daemon restarts.",
            }
'''
source = source[:start] + new + source[end:]
# Existing get-result handler already consults durable receipts when no in-memory job exists.
path.write_text(source, encoding="utf-8")
print("Patched only synapse_run_command_async dispatch to use detached supervisor")
