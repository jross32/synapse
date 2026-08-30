from __future__ import annotations

from pathlib import Path

from synapse_daemon import watchdogs


def test_snapshot_builds_protection_chain_and_console_risk(monkeypatch, tmp_path: Path) -> None:
    log = tmp_path / "watch.log"
    log.write_text("started\nhealthy\n", encoding="utf-8")

    specs = [
        watchdogs.WatchdogSpec(
            id="service",
            name="Service",
            kind="service",
            description="target",
            command_any=(("service-token",),),
            log_path=log,
        ),
        watchdogs.WatchdogSpec(
            id="guard",
            name="Guard",
            kind="watchdog",
            description="protects target",
            command_any=(("guard-token",),),
            task_names=("GuardTask",),
            protects=("service",),
            log_path=log,
        ),
    ]
    monkeypatch.setattr(watchdogs, "default_specs", lambda _data_dir: specs)
    monkeypatch.setattr(
        watchdogs,
        "_process_inventory",
        lambda: [
            {
                "pid": 101,
                "name": "pythonw.exe",
                "command_line": "service-token",
                "match_text": "pythonw.exe service-token",
                "status": "running",
                "uptime_seconds": 50,
            },
            {
                "pid": 202,
                "name": "pythonw.exe",
                "command_line": "guard-token",
                "match_text": "pythonw.exe guard-token",
                "status": "running",
                "uptime_seconds": 30,
            },
        ],
    )
    monkeypatch.setattr(
        watchdogs,
        "_task_inventory",
        lambda _names: {
            "GuardTask": {
                "task_name": "GuardTask",
                "state": "Running",
                "hidden": True,
                "logon_mode": "Interactive only",
                "last_run_time": "now",
                "next_run_time": "N/A",
                "last_task_result": 267009,
                "task_to_run": "pythonw.exe guard.py",
            }
        },
    )

    result = watchdogs.snapshot_watchdogs(tmp_path, force=True)

    assert result["counts"] == {
        "total": 2,
        "healthy": 2,
        "armed": 0,
        "warning": 0,
        "stopped": 0,
        "console_risk": 0,
    }
    by_id = {item["id"]: item for item in result["items"]}
    assert by_id["guard"]["protects"] == ["service"]
    assert by_id["service"]["protected_by"] == ["guard"]
    assert by_id["guard"]["latest_log_line"] == "healthy"
    assert by_id["guard"]["log_available"] is True


def test_periodic_ready_task_is_armed_not_stopped() -> None:
    spec = watchdogs.WatchdogSpec(
        id="periodic",
        name="Periodic",
        kind="watchdog",
        description="periodic",
        expected_long_running=False,
    )
    task = {"state": "Ready"}

    assert watchdogs._health(spec, [], task) == "armed"


def test_log_tail_is_bounded(tmp_path: Path) -> None:
    log = tmp_path / "events.log"
    log.write_text("\n".join(f"line-{i}" for i in range(20)) + "\n", encoding="utf-8")

    assert watchdogs._tail(log, 3) == ["line-17", "line-18", "line-19"]
