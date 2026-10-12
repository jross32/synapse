"""Durable restart maintenance barrier. Never terminates or suspends OS processes."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

LOCK = threading.RLock()
TERMINAL = {"cancelled", "ready", "postponed"}
CAPABILITIES = {"checkpoint", "drain", "non_pausable"}
ACKS = {"paused", "drained", "unsafe"}

class MaintenanceError(ValueError):
    pass

class MaintenanceCoordinator:
    """Tracks explicit worker acknowledgements. Conservative fail-closed restart gate.

    Snapshots an immutable worker roster when maintenance is requested; pending or
    unsafe workers never count as safely paused. Two minutes is a grace deadline,
    not permission to kill or bypass work.
    """

    def __init__(self, data_dir: str | Path, clock=time.time):
        self.path = Path(data_dir) / "maintenance" / "restart.json"
        self.clock = clock

    def _load(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != 1:
            raise MaintenanceError("Unsupported maintenance state")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".restart-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"), sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _state(self, d: dict[str, Any] | None) -> dict[str, Any] | None:
        if d is None:
            return None
        if d["status"] == "preparing":
            workers = d["workers"]
            if all(w["ack"] in ("paused", "drained") for w in workers.values()):
                d["status"] = "ready"
                d["ready_at"] = self.clock()
                self._save(d)
            elif self.clock() >= d["deadline"]:
                d["status"] = "postponed"
                d["reason"] = "One or more workers did not acknowledge a safe checkpoint before the grace deadline."
                self._save(d)
        return d

    def inspect(self) -> dict[str, Any] | None:
        with LOCK:
            return self._state(self._load())

    def prepare(self, workers: list[dict[str, str]], grace_seconds: int = 120) -> dict[str, Any]:
        if not 5 <= grace_seconds <= 900:
            raise MaintenanceError("Grace period must be 5-900 seconds")
        roster: dict[str, dict[str, Any]] = {}
        for w in workers:
            worker_id = w.get("id")
            capability = w.get("capability")
            if not isinstance(worker_id, str) or not worker_id or len(worker_id) > 180:
                raise MaintenanceError("Worker ID invalid")
            if worker_id in roster or capability not in CAPABILITIES:
                raise MaintenanceError("Duplicate worker ID or invalid capability")
            roster[worker_id] = {"capability": capability, "ack": None, "checkpoint": None}
        if not roster:
            raise MaintenanceError("Worker roster cannot be empty without trusted discovery")
        with LOCK:
            previous = self._state(self._load())
            if previous and previous["status"] in {"preparing", "ready"}:
                raise MaintenanceError("A maintenance window is already open")
            now = self.clock()
            data = {"schema": 1, "id": uuid.uuid4().hex, "status": "preparing",
                    "started_at": now, "deadline": now + grace_seconds, "workers": roster,
                    "reason": None, "ready_at": None}
            self._save(data)
            return self._state(data)

    def acknowledge(self, operation_id: str, worker_id: str, status: str,
                    checkpoint: str | None = None) -> dict[str, Any]:
        with LOCK:
            data = self._state(self._load())
            if not data or data["id"] != operation_id or data["status"] != "preparing":
                raise MaintenanceError("Maintenance is missing or not preparing")
            worker = data["workers"].get(worker_id)
            if worker is None or status not in ACKS:
                raise MaintenanceError("Unknown worker or invalid acknowledgement")
            if status == "paused" and worker["capability"] != "checkpoint":
                raise MaintenanceError("Worker cannot claim an unsupported checkpoint")
            if status == "paused" and (not checkpoint or len(checkpoint) > 1000):
                raise MaintenanceError("A durable checkpoint reference is required")
            if worker["capability"] == "non_pausable" and status != "unsafe":
                raise MaintenanceError("Non-pausable worker must block restart")
            if worker["ack"] is not None:
                raise MaintenanceError("Worker already acknowledged")
            worker["ack"] = status
            worker["checkpoint"] = checkpoint if status == "paused" else None
            if status == "unsafe":
                data["status"] = "postponed"
                data["reason"] = f"Worker {worker_id} cannot pause safely"
            self._save(data)
            return self._state(data)

    def commit_ready(self, operation_id: str) -> dict[str, Any]:
        """Consume readiness exactly once; a second commit must not restart again."""
        with LOCK:
            data = self._state(self._load())
            if not data or data["id"] != operation_id or data["status"] != "ready":
                raise MaintenanceError("Restart blocked: maintenance is not ready or already committed")
            # Snapshot stays durable even if Electron/daemon dies after accepting commit.
            data["status"] = "committed"
            data["committed_at"] = self.clock()
            self._save(data)
            return data

    def cancel(self, operation_id: str) -> dict[str, Any]:
        with LOCK:
            data = self._load()
            if not data or data["id"] != operation_id:
                raise MaintenanceError("Unknown maintenance operation")
            if data["status"] not in {"preparing", "ready", "postponed"}:
                raise MaintenanceError("Maintenance already finalized")
            data["status"] = "cancelled"
            self._save(data)
            return data

    def require_ready(self, operation_id: str) -> dict[str, Any]:
        data = self.inspect()
        if not data or data["id"] != operation_id or data["status"] != "ready":
            raise MaintenanceError("Restart blocked: workers have not all acknowledged a safe pause")
        return data
