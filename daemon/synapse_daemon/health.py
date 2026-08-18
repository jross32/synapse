"""Health-check protocol per project (Contract #17).

Every project carries one ``HealthProbe``; the daemon polls it on a separate
cadence from process liveness so the UI can render a second state-pill:
"alive but unhealthy". Skeleton only — actual polling loop wires in during
Milestone E.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from .time_utils import utc_now


class HealthState(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    MISCONFIGURED = "misconfigured"
    """The app answered, but the probe itself is wrong - e.g. the URL 404s.

    Kept apart from UNHEALTHY because they need opposite fixes and looked identical for as
    long as this existed. `wbscrper` was configured to poll `/api/status`, which that server
    has never served: the app was up and serving on its port, the probe 404'd, and nothing
    distinguished "your app is broken" from "your health URL is wrong".
    """


class HealthProbe(BaseModel):
    """Declarative health probe — one per project."""

    kind: Literal["none", "http", "tcp", "command"] = "none"
    target: str | None = Field(
        default=None,
        description="URL for http, port number for tcp, shell command for command.",
    )
    interval_seconds: int = Field(default=15, ge=1, le=3600)
    timeout_seconds: int = Field(default=5, ge=1, le=60)
    expect_status: int | None = Field(
        default=200,
        description="HTTP status to consider healthy. Only meaningful when kind='http'.",
    )
    consecutive_failures_to_unhealthy: int = Field(default=3, ge=1, le=20)


class HealthSnapshot(BaseModel):
    """Latest probe result for one project."""

    project_id: str
    state: HealthState = HealthState.UNKNOWN
    last_probed_at: datetime | None = None
    last_state_change_at: datetime = Field(default_factory=utc_now)
    consecutive_failures: int = 0
    last_error: str | None = None


def is_terminal(state: HealthState) -> bool:
    """A terminal health state (other than ``UNKNOWN``) — used by UI badges."""

    return state in (HealthState.HEALTHY, HealthState.UNHEALTHY)


def probe_once(probe: HealthProbe) -> tuple[HealthState, str]:
    """Run one health probe and say what happened.

    Returns the state plus a human-readable detail, because "unhealthy" on its own has never
    been enough to act on.

    A 4xx other than 408/429 is reported as MISCONFIGURED rather than UNHEALTHY: the server
    answered, so the process is alive, and it said this route does not exist. That is a
    problem with the probe, not the app, and telling them apart is the whole point.
    """
    import socket
    import subprocess
    import urllib.error
    import urllib.request

    target = (probe.target or "").strip()
    if probe.kind == "none" or not target:
        return HealthState.UNKNOWN, "no health probe configured"

    if probe.kind == "http":
        expected = probe.expect_status or 200
        try:
            with urllib.request.urlopen(target, timeout=probe.timeout_seconds) as resp:
                code = resp.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        except Exception as exc:  # noqa: BLE001 -- connection refused, DNS, timeout
            return HealthState.UNHEALTHY, f"{type(exc).__name__}: {exc}"
        if code == expected:
            return HealthState.HEALTHY, f"{target} returned {code}"
        if 400 <= code < 500 and code not in (408, 429):
            return (HealthState.MISCONFIGURED,
                    f"{target} returned {code}: the app is up but that endpoint does not "
                    f"exist. Point the probe at one that does.")
        return HealthState.UNHEALTHY, f"{target} returned {code}, expected {expected}"

    if probe.kind == "tcp":
        try:
            port = int(target.rsplit(":", 1)[-1])
        except ValueError:
            return HealthState.MISCONFIGURED, f"{target!r} is not a port number"
        host = target.rsplit(":", 1)[0] if ":" in target else "127.0.0.1"
        try:
            with socket.create_connection((host, port), timeout=probe.timeout_seconds):
                return HealthState.HEALTHY, f"{host}:{port} accepted a connection"
        except Exception as exc:  # noqa: BLE001
            return HealthState.UNHEALTHY, f"{host}:{port}: {exc}"

    if probe.kind == "command":
        try:
            done = subprocess.run(target, shell=True, capture_output=True, text=True,
                                  timeout=probe.timeout_seconds)
        except subprocess.TimeoutExpired:
            return HealthState.UNHEALTHY, f"command did not finish in {probe.timeout_seconds}s"
        except Exception as exc:  # noqa: BLE001
            return HealthState.MISCONFIGURED, f"could not run the command: {exc}"
        if done.returncode == 0:
            return HealthState.HEALTHY, "command exited 0"
        return HealthState.UNHEALTHY, (done.stderr or done.stdout or "")[-200:].strip() or             f"command exited {done.returncode}"

    return HealthState.MISCONFIGURED, f"unknown probe kind {probe.kind!r}"
