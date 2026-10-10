"""Safe one-shot Railway telemetry poll for Windows Task Scheduler.

Does not print or store API credentials, and records only state transitions.
Never deploys, scales or pauses a service.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "daemon"))
from synapse_daemon.railway_cost_monitor import get_status, _json_file, _write_json


def main() -> int:
    data = ROOT / "data"
    state_path = data / "railway-costs" / "last-poll.json"
    state = get_status(data, refresh=True)
    previous = _json_file(state_path, {})
    record = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "state": state["state"],
        "estimated_monthly_baseline_usd": state["estimated_monthly_baseline_usd"],
        "source": state["source"],
        "connected": state["connected_for_auto_refresh"],
        "billing_total_verified": state["billing_total_verified"],
        "observation_age_seconds": state["observation_age_seconds"],
        "refresh_failed": bool(state["refresh_error"]),
    }
    _write_json(state_path, record)
    if state["state"] in ("warning", "critical") and (
        previous.get("state") != state["state"] or
        previous.get("estimated_monthly_baseline_usd") != record["estimated_monthly_baseline_usd"]
    ):
        with (data / "railway-costs" / "alerts.jsonl").open("a", encoding="utf-8") as dest:
            dest.write(json.dumps(record) + "\n")
    print(json.dumps(record))
    return 0 if record["connected"] and not record["refresh_failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
