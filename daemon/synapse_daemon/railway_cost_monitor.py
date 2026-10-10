"""Railway resource and cost guard for the Synapse Watchdogs dashboard.

Explicitly separates short-window metrics, forward-looking resource estimates, and
Railway's authoritative billing totals (which this endpoint does not retrieve).
No destructive Railway operations; token is read from the process environment only.
"""
from __future__ import annotations

import json
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .railway_credential import read_railway_token

PRICE_CPU_MONTH = 20.0
PRICE_RAM_MONTH = 10.0
PRICE_VOLUME_MONTH = 0.15
PRICE_EGRESS_GB = 0.05
KNOWN_PRICES_URL = "https://docs.railway.com/pricing/plans"
API_ENDPOINT = "https://backboard.railway.com/graphql/v2"
DEFAULT_WARN_USD = 3.0
DEFAULT_CRITICAL_USD = 5.0
_CACHE_SECONDS = 300
_guard = threading.RLock()
_METRICS_QUERY = """
query SynapseRailwayMetrics($environmentId: String!, $serviceId: String!,
  $startDate: DateTime!, $measurements: [MetricMeasurement!]!) {
  metrics(environmentId: $environmentId, serviceId: $serviceId,
    startDate: $startDate, measurements: $measurements) {
    measurement values { ts value }
  }
}
"""

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _iso_now() -> str:
    return _now().isoformat()

def _when(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def _json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default

def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)

def default_config() -> dict[str, Any]:
    return {
        "workspace": "jross32's Projects",
        "warning_usd": DEFAULT_WARN_USD,
        "critical_usd": DEFAULT_CRITICAL_USD,
        "services": [
            {
                "name": "accounts-api",
                "project": "Synapse Accounts",
                "project_id": "80d74326-05c7-4ad6-b6fa-4fcde1ecee45",
                "environment_id": "29a6cc01-17b9-45a6-bcc9-d2ec00426b0c",
                "service_id": "6427cc2c-1837-4795-addd-0b97480b6a65",
                "volume_gb_allocated": 0.5,
                "purpose": "Authentication, Google login and future multi-device identity",
            }
        ],
        "inactive_projects": ["SYNAPS-OS Clinic OS Staging"],
    }

def _paths(data_dir: Path) -> tuple[Path, Path]:
    root = data_dir / "railway-costs"
    return root / "config.json", root / "observation.json"

def load_config(data_dir: Path) -> dict[str, Any]:
    config_path, _ = _paths(data_dir)
    saved = _json_file(config_path, {})
    result = default_config()
    if isinstance(saved, dict):
        result.update({key: value for key, value in saved.items() if key in result})
    return result

def update_thresholds(data_dir: Path, warning: float, critical: float) -> dict[str, Any]:
    if (not all(math.isfinite(v) for v in (warning, critical)) or
            not 0 < warning < critical <= 100000):
        raise ValueError("Require 0 < warning < critical <= 100000 USD")
    with _guard:
        cfg = load_config(data_dir)
        cfg["warning_usd"] = round(warning, 2)
        cfg["critical_usd"] = round(critical, 2)
        _write_json(_paths(data_dir)[0], cfg)
        return cfg

def save_observation(data_dir: Path, observation: dict[str, Any]) -> None:
    if not isinstance(observation.get("services"), list):
        raise ValueError("services must be a list")
    if not _when(observation.get("observed_at")):
        raise ValueError("observed_at must be ISO timestamp")
    with _guard:
        _write_json(_paths(data_dir)[1], observation)

def _post_graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = Request(API_ENDPOINT, payload, {
        "Content-Type": "application/json", "Authorization": f"Bearer {token}"
    }, method="POST")
    try:
        with urlopen(req, timeout=9) as res:
            body = json.load(res)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Railway metrics request failed; check token access/network") from exc
    if not isinstance(body, dict) or body.get("errors") or not isinstance(body.get("data"), dict):
        raise RuntimeError("Railway rejected the metrics query or permissions")
    return body["data"]

def parse_metrics(payload: dict[str, Any]) -> dict[str, float | None]:
    """Most recent observed CPU, RAM, disk; egress is WINDOW total, not invoice."""
    buckets: dict[str, list[tuple[float, float]]] = {}
    for entry in payload.get("metrics", []):
        name = entry.get("measurement")
        if name not in ("CPU_USAGE", "MEMORY_USAGE_GB", "DISK_USAGE_GB", "NETWORK_TX_GB"):
            continue
        for point in entry.get("values", []):
            try:
                t = float(point["ts"])
                n = float(point["value"])
            except (ValueError, TypeError, KeyError):
                continue
            if math.isfinite(n) and n >= 0:
                buckets.setdefault(name, []).append((t, n))
    result: dict[str, float | None] = {}
    for source, target in [("CPU_USAGE", "cpu_vcpu"), ("MEMORY_USAGE_GB", "ram_gb"),
                           ("DISK_USAGE_GB", "disk_used_gb")]:
        samples = sorted(buckets.get(source, []))
        if samples:
            last_ts = samples[-1][0]
            recent = [v for ts, v in samples if ts >= last_ts - 600]
            result[target] = round(sum(recent) / len(recent), 8) if recent else None
        else:
            result[target] = None
    net = buckets.get("NETWORK_TX_GB", [])
    result["network_tx_gb_observed_window"] = round(sum(v for _, v in net), 8) if net else None
    return result

def fetch_observation(config: dict[str, Any], token: str) -> dict[str, Any]:
    start = (_now() - timedelta(hours=1)).isoformat()
    services = []
    for spec in config["services"]:
        data = _post_graphql(token, _METRICS_QUERY, {
            "environmentId": spec["environment_id"],
            "serviceId": spec["service_id"],
            "startDate": start,
            "measurements": ["CPU_USAGE", "MEMORY_USAGE_GB", "DISK_USAGE_GB", "NETWORK_TX_GB"],
        })
        metrics = parse_metrics(data)
        services.append({
            **spec, **metrics, "source": "railway_graphql_metrics_1h",
        })
    return {
        "observed_at": _iso_now(),
        "source": "railway_graphql_metrics_1h",
        "services": services,
        "billing_total_usd": None,
        "billing_source": "not_connected",
    }

def _nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None

def calculate_status(config: dict[str, Any], observation: dict[str, Any] | None, *, connected: bool,
                     refresh_error: str | None = None) -> dict[str, Any]:
    observed = _when(observation.get("observed_at")) if observation else None
    age = max(0, (_now() - observed).total_seconds()) if observed else None
    fresh = age is not None and age < 3600
    services = []
    estimate = 0.0
    complete = bool(observation and observation.get("services"))
    for raw in (observation or {}).get("services", []):
        cpu = _nonnegative(raw.get("cpu_vcpu"))
        ram = _nonnegative(raw.get("ram_gb"))
        disk = _nonnegative(raw.get("disk_used_gb"))
        if cpu is None or ram is None or disk is None:
            monthly = None
            complete = False
        else:
            monthly = round(cpu * PRICE_CPU_MONTH + ram * PRICE_RAM_MONTH +
                            disk * PRICE_VOLUME_MONTH, 4)
            estimate += monthly
        services.append({
            "name": str(raw.get("name", "")),
            "project": str(raw.get("project", "")),
            "purpose": str(raw.get("purpose", "")),
            "cpu_vcpu": cpu,
            "ram_gb": ram,
            "disk_used_gb": _nonnegative(raw.get("disk_used_gb")),
            "volume_gb_allocated": disk,
            "network_tx_gb_observed_window": _nonnegative(raw.get("network_tx_gb_observed_window")),
            "baseline_usd_month": monthly,
            "source": str(raw.get("source", (observation or {}).get("source", "unknown"))),
        })
    estimate_result = round(estimate, 2) if complete else None
    warning = float(config["warning_usd"])
    critical = float(config["critical_usd"])
    if not fresh:
        state = "stale" if observed else "not_configured"
    elif estimate_result is None:
        state = "incomplete"
    elif estimate_result >= critical:
        state = "critical"
    elif estimate_result >= warning:
        state = "warning"
    else:
        state = "healthy"
    return {
        "workspace": config["workspace"],
        "observed_at": observed.isoformat() if observed else None,
        "observation_age_seconds": round(age) if age is not None else None,
        "connected_for_auto_refresh": connected,
        "refresh_error": refresh_error,
        "state": state,
        "warning_usd": warning,
        "critical_usd": critical,
        "estimated_monthly_baseline_usd": estimate_result,
        "estimate_covers": "Observed steady-state CPU, RAM, and reported used disk; assumes 24/7 similar load",
        "not_in_estimate": ["network egress", "other workspace projects", "Railway Agent usage",
                            "backups", "taxes", "any plan subscription minimum"],
        "billing_total_usd": (observation or {}).get("billing_total_usd"),
        "billing_total_verified": False,
        "source": (observation or {}).get("source", "not_available"),
        "services": services,
        "inactive_projects": config.get("inactive_projects", []),
        "prices_url": KNOWN_PRICES_URL,
    }

def get_status(data_dir: Path, *, refresh: bool = False) -> dict[str, Any]:
    token = read_railway_token(data_dir)
    with _guard:
        config = load_config(data_dir)
        observation = _json_file(_paths(data_dir)[1], None)
        observed_at = _when(observation.get("observed_at")) if isinstance(observation, dict) else None
        should_refresh = token and (refresh or not observed_at or
            (_now() - observed_at).total_seconds() > _CACHE_SECONDS)
        error = None
        if should_refresh:
            try:
                observation = fetch_observation(config, token)
                save_observation(data_dir, observation)
            except (ValueError, RuntimeError, KeyError) as exc:
                error = str(exc)
        return calculate_status(config, observation if isinstance(observation, dict) else None,
                                connected=bool(token), refresh_error=error)
