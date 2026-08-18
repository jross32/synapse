"""Health probes that actually run, and tell a wrong URL from a broken app.

`HealthProbe` was in the project model from the beginning and `projects.set_health` was
written to record the outcome, but nothing ever called either - `set_health` had one caller
in the whole repo and it was a test. Every project sat at `current_health: "unknown"` with
`last_health_at: null` forever, so no health target could work however correct it was.
"""

from __future__ import annotations

import http.server
import threading

import pytest

from synapse_daemon.health import HealthProbe, HealthState, probe_once


@pytest.fixture()
def server():
    """A real server: a probe verified only against mocks proves nothing about HTTP."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            code = {"/api/health": 200, "/api/status": 404, "/boom": 503}.get(self.path, 404)
            self.send_response(code)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):  # keep pytest output clean
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_a_working_endpoint_is_healthy(server):
    state, detail = probe_once(HealthProbe(kind="http", target=f"{server}/api/health"))
    assert state is HealthState.HEALTHY
    assert "200" in detail


def test_a_404_is_misconfigured_not_unhealthy(server):
    """The exact bug: the app was up, the probe URL was wrong, and they looked the same."""
    state, detail = probe_once(HealthProbe(kind="http", target=f"{server}/api/status"))
    assert state is HealthState.MISCONFIGURED, "a wrong URL is not a broken app"
    assert "does not exist" in detail


def test_a_5xx_is_unhealthy(server):
    """The app answered and said it is broken. That is the app's problem, not the probe's."""
    state, _ = probe_once(HealthProbe(kind="http", target=f"{server}/boom"))
    assert state is HealthState.UNHEALTHY


def test_nothing_listening_is_unhealthy():
    state, detail = probe_once(
        HealthProbe(kind="http", target="http://127.0.0.1:9/never", timeout_seconds=2))
    assert state is HealthState.UNHEALTHY
    assert detail


def test_no_probe_configured_stays_unknown():
    """Absence of a probe is not a verdict; it must not read as healthy or as broken."""
    assert probe_once(HealthProbe(kind="none"))[0] is HealthState.UNKNOWN
    assert probe_once(HealthProbe(kind="http", target=""))[0] is HealthState.UNKNOWN


def test_tcp_probe(server):
    port = server.rsplit(":", 1)[-1]
    assert probe_once(HealthProbe(kind="tcp", target=port))[0] is HealthState.HEALTHY
    assert probe_once(HealthProbe(kind="tcp", target="9"))[0] is HealthState.UNHEALTHY
    assert probe_once(HealthProbe(kind="tcp", target="nope"))[0] is HealthState.MISCONFIGURED


def test_command_probe():
    assert probe_once(HealthProbe(kind="command", target="exit 0"))[0] is HealthState.HEALTHY
    assert probe_once(HealthProbe(kind="command", target="exit 3"))[0] is HealthState.UNHEALTHY
