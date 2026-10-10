"""Railway cost guard regression tests (offline, no secrets or network)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse_daemon import railway_cost_monitor as monitor
from synapse_daemon.routes_watchdogs import build_watchdogs_router


def sample(cpu=0.01, ram=0.1, volume=0.5):
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source": "test-observation",
        "services": [{
            "name": "accounts-api", "project": "Synapse Accounts",
            "cpu_vcpu": cpu, "ram_gb": ram, "volume_gb_allocated": volume, "disk_used_gb": volume,
            "network_tx_gb_observed_window": 0.004,
        }],
    }


def test_estimates_cpu_ram_used_volume_not_egress():
    result = monitor.calculate_status(monitor.default_config(), sample(0.25, 0.5, 0.5), connected=False)
    assert result["estimated_monthly_baseline_usd"] == 10.07  # 5 + 5 + 0.075 rounded
    assert result["billing_total_verified"] is False
    assert "network egress" in result["not_in_estimate"]
    assert result["state"] == "critical"


def test_warning_and_healthy_are_threshold_based():
    cfg = monitor.default_config()
    assert monitor.calculate_status(cfg, sample(0.1, 0.2), connected=False)["state"] == "warning"
    assert monitor.calculate_status(cfg, sample(0.005, 0.06), connected=False)["state"] == "healthy"


def test_incomplete_never_becomes_free_estimate():
    result = monitor.calculate_status(monitor.default_config(), sample(None, 0.08), connected=False)
    assert result["state"] == "incomplete"
    assert result["estimated_monthly_baseline_usd"] is None


def test_stale_data_is_not_healthy_even_when_cheap():
    value = sample()
    value["observed_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert monitor.calculate_status(monitor.default_config(), value, connected=False)["state"] == "stale"


@pytest.mark.parametrize("warn,critical", [
    (-1, 5), (5, 5), (5, 4), (1, 100001), (float("nan"), 5), (3, float("inf")),
])
def test_invalid_thresholds_do_not_save(tmp_path, warn, critical):
    with pytest.raises(ValueError):
        monitor.update_thresholds(tmp_path, warn, critical)
    assert not (tmp_path / "railway-costs" / "config.json").exists()


def test_thresholds_persist_and_observation_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("RAILWAY_API_TOKEN", raising=False)
    cfg = monitor.update_thresholds(tmp_path, 2.25, 4.5)
    assert cfg["warning_usd"] == 2.25
    assert monitor.load_config(tmp_path)["critical_usd"] == 4.5
    monitor.save_observation(tmp_path, sample())
    result = monitor.get_status(tmp_path)
    assert result["state"] == "healthy"
    assert result["connected_for_auto_refresh"] is False


def test_parse_railway_graphql_metrics_last_10m_average():
    payload = {"metrics": [
        {"measurement": "CPU_USAGE", "values": [{"ts": 100, "value": 0.1}, {"ts": 800, "value": 0.3}]},
        {"measurement": "MEMORY_USAGE_GB", "values": [{"ts": 800, "value": 0.05}]},
        {"measurement": "DISK_USAGE_GB", "values": [{"ts": 800, "value": 0.03}]},
        {"measurement": "NETWORK_TX_GB", "values": [{"ts": 400, "value": 0.002}, {"ts": 800, "value": 0.004}]},
    ]}
    result = monitor.parse_metrics(payload)
    assert result["cpu_vcpu"] == pytest.approx(0.3)
    assert result["ram_gb"] == pytest.approx(0.05)
    assert result["network_tx_gb_observed_window"] == pytest.approx(0.006)


def test_no_token_no_automatic_railway_api_request(tmp_path, monkeypatch):
    monkeypatch.delenv("RAILWAY_API_TOKEN", raising=False)
    monkeypatch.setattr(monitor, "fetch_observation", lambda *_: pytest.fail("unexpected network call"))
    monitor.save_observation(tmp_path, sample())
    assert monitor.get_status(tmp_path, refresh=True)["state"] == "healthy"


def test_api_budget_update_and_read(tmp_path, monkeypatch):
    monkeypatch.delenv("RAILWAY_API_TOKEN", raising=False)
    app = FastAPI()
    app.include_router(build_watchdogs_router(tmp_path), prefix="/api/v1")
    monitor.save_observation(tmp_path, sample())
    client = TestClient(app)
    response = client.get("/api/v1/system/railway-costs")
    assert response.status_code == 200
    assert response.json()["services"][0]["name"] == "accounts-api"
    changed = client.post("/api/v1/system/railway-costs/budget",
                          json={"warning_usd": 1.5, "critical_usd": 4.5})
    assert changed.status_code == 200
    assert changed.json()["warning_usd"] == 1.5
    assert client.post("/api/v1/system/railway-costs/budget",
                       json={"warning_usd": 5, "critical_usd": 3}).status_code == 422
