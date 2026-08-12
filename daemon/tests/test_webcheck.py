"""Tests for the render-and-attack gate.

This module had no tests, which is how a JavaScript **syntax error** survived inside
``_detect_token_key``: the snippet joined script contents on a newline written as a real
line break inside a JS string literal. ``page.evaluate`` threw, the surrounding ``except``
swallowed it, and the function returned its fallback constant on every call it ever made.

It looked like detection. It was a hardcoded ``"app_token"`` - the precise assumption the
function's own docstring exists to warn against. Downstream, that meant the probe
authenticated as nobody, so every logged-in view was graded as the login page it redirects
to, and an app whose dashboard throws on load was reported as having no console errors.

A check that cannot fail is not a check, and one that silently degrades into a constant is
worse than none at all: it occupies the place where a real check would have gone.
"""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from synapse_daemon.scaffold import webcheck

playwright = pytest.importorskip("playwright.async_api",
                                 reason="the browser checks need playwright")

WITH_KEY = """<!doctype html><html><head><title>t</title></head><body>
<h1>App</h1>
<script>
  const t = localStorage.getItem('tm_token');
  function save(v) { localStorage.setItem('tm_token', v); }
</script>
</body></html>"""

NO_KEY = """<!doctype html><html><head><title>t</title></head><body>
<h1>App</h1><script>console.log('nothing stored here');</script></body></html>"""


def _serve(html: str):
    """A one-page server, so detection is exercised against a real document."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # noqa: A002
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


async def _detect(html: str) -> str:
    server, base = _serve(html)
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await (await browser.new_context()).new_page()
                return await webcheck._detect_token_key(page, base, "/")
            finally:
                await browser.close()
    finally:
        server.shutdown()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_detects_the_apps_own_token_key():
    """The regression. This returned 'app_token' for every page ever passed to it."""
    assert _run(_detect(WITH_KEY)) == "tm_token"


def test_reports_nothing_found_rather_than_a_plausible_default():
    """An empty result is what lets the caller tell detection apart from a guess."""
    assert _run(_detect(NO_KEY)) == ""


def test_unique_email_gives_a_fresh_account_each_run():
    """A fixed probe address works once, then 409s forever after.

    The flow declares one literal address. Builds are graded repeatedly against the same
    database, so from the second run onward signup fails and the hostile-input probe
    reports `not_run` - present in the report, never actually executed.
    """
    a = webcheck._unique_email("probe@probe.test")
    b = webcheck._unique_email("probe@probe.test")
    assert a != b
    assert a.endswith("@probe.test")
    assert a.startswith("probe+")


def test_unique_email_survives_a_template_without_a_domain():
    assert "@" in webcheck._unique_email("probe")


def test_every_path_through_the_verdict_reports_both_checks():
    """A check missing from the report is indistinguishable from one that passed."""
    report = webcheck.WebCheckReport()
    _run(webcheck._xss_verdict(None, "http://127.0.0.1:1", {"view": "/dashboard"},
                               report, "signup returned no token"))
    names = {r.name for r in report.results}
    assert names == {"stored XSS probe", "records render in the view"}
    assert all(r.status == "not_run" for r in report.results)


def test_a_report_with_a_failure_is_not_passing():
    report = webcheck.WebCheckReport()
    report.add("stored XSS probe", "pass")
    report.add("records render in the view", "fail", "nothing rendered")
    assert not report.passed
    assert "nothing rendered" in report.as_repair_text()


def test_not_run_never_counts_as_passing():
    """The rule the whole module is built on."""
    report = webcheck.WebCheckReport()
    report.add("stored XSS probe", "not_run", "playwright missing")
    assert report.passed, "not_run is not a failure"
    assert not any(r.ok for r in report.results), "not_run must not be counted as a pass"
