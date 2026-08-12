"""Prove the XSS probe can fail a vulnerable app, by serving one and attacking it.

This is the gate the plan named first, and it had never been run: *"Run webcheck against a
known-bad app — it must FAIL. A checker that passes a known-bad app is worthless, so this is
the gate before anything else is trusted."*

The existing `test_webcheck.py` covers the helpers - token-key detection, verdict arithmetic,
email uniqueness. All useful, none of it evidence that the probe fires. That distinction has
now bitten this project twice: a render check that graded the wrong page, and acceptance
scenarios that were present in the test file and never executed. Testing that a check is
*wired* is not testing that it *works*.

So both apps here are real, served over a real port, driven by a real browser. The only
difference between them is one line: whether user text reaches the DOM through `textContent`
or `innerHTML`.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from synapse_daemon.scaffold import webcheck as webcheck_mod

pytest.importorskip("playwright.sync_api")
pytest.importorskip("fastapi")

# One template, one substitution. Keeping the two apps otherwise byte-identical means a
# difference in verdict can only be caused by the escaping, not by anything incidental.
APP_TEMPLATE = '''
import argparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()
ROWS: list[dict] = []
TOKENS: dict[str, int] = {}


class Creds(BaseModel):
    email: str
    password: str


class Row(BaseModel):
    name: str = ""
    title: str = ""
    distance_km: float = 0.0
    amount: float = 0.0
    date: str = ""


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/signup", status_code=201)
async def signup(body: Creds):
    TOKENS["tok-1"] = 1
    return {"token": "tok-1"}


@app.post("/api/trails", status_code=201)
async def create(body: Row, request: Request):
    if request.headers.get("authorization", "") != "Bearer tok-1":
        return {"error": "no"}
    ROWS.append({"id": len(ROWS) + 1, "name": body.name or body.title})
    return ROWS[-1]


@app.get("/api/trails")
async def listing():
    return ROWS


PAGE = """<!doctype html>
<html><head>__VIEWPORT__
<style>__BTNCSS__</style></head>
<body>
  __LABELS__
  <button>Go</button>
  __OVERFLOW__
  __PLACEHOLDER__
  <ul id="rows"></ul>
  <script>
    fetch('/api/trails').then(r => r.json()).then(rows => {{
      const ul = document.getElementById('rows');
      for (const row of rows) {{
        const li = document.createElement('li');
        li.__SINK__ = row.name;
        ul.appendChild(li);
      }}
    }});
  </script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(PAGE)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(PAGE)


@app.get("/signup", response_class=HTMLResponse)
async def signup_page():
    return HTMLResponse(PAGE)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(PAGE)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8123)
    args = ap.parse_args()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="critical")
'''


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_health(base: str, deadline: float) -> bool:
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    return False


# The page varies along one axis at a time, so a verdict can only be caused by the defect
# under test. WELL_BUILT is what the UI kit produces; DEFECTIVE is each of the things the
# accessibility and layout checks exist to catch.
WELL_BUILT = {
    "__VIEWPORT__": '<meta name="viewport" content="width=device-width, initial-scale=1">',
    "__BTNCSS__": "button, a { min-height: 44px; display: inline-block; }",
    "__LABELS__": ('<label for="email">Email address</label>'
                   '<input id="email" name="email" type="email">\n'
                   '  <label for="password">Password</label>'
                   '<input id="password" name="password" type="password">'),
    "__OVERFLOW__": "",
    "__PLACEHOLDER__": "",
}

DEFECTIVE = {
    "__VIEWPORT__": '<meta name="viewport" content="width=device-width, initial-scale=1">',
    # 20px tall: a real tap target on a phone is 44.
    "__BTNCSS__": "button, a { height: 20px; min-height: 0; display: inline-block; }",
    # Inputs with no <label for> and no aria-label - invisible to a screen reader.
    "__LABELS__": ('<input id="email" name="email" type="email">\n'
                   '  <input id="password" name="password" type="password">'),
    "__OVERFLOW__": '<div style="width: 2000px; height: 8px;"></div>',
    # The literal string a template prints when it reads a field that does not exist.
    "__PLACEHOLDER__": "<p>Distance: undefined km</p>",
}


def _render(sink: str, variant: dict[str, str]) -> str:
    src = APP_TEMPLATE.replace("__SINK__", sink)
    for token, value in variant.items():
        src = src.replace(token, value)
    return src


def _serve(tmp_path: Path, sink: str, variant: dict[str, str] | None = None):
    """Write the app with the chosen DOM sink, serve it, return (base_url, process)."""
    app_file = tmp_path / f"app_{sink}_{'defective' if variant is DEFECTIVE else 'ok'}.py"
    app_file.write_text(_render(sink, variant or WELL_BUILT), encoding="utf-8")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-B", app_file.name, "--port", str(port)],
                            cwd=str(tmp_path), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    if not _wait_for_health(base, time.time() + 45):
        proc.kill()
        out = proc.stdout.read()[-800:] if proc.stdout else ""
        pytest.fail(f"the {sink} fixture never came up: {out}")
    return base, proc


def _check(base: str):
    flow = webcheck_mod.default_flow()
    flow["view"] = "/dashboard"
    return asyncio.run(webcheck_mod.check_app(base, pages=["/", "/signup", "/dashboard"],
                                              flow=flow))


def _verdict(report, name: str) -> str:
    status = next((r.status for r in report.results if r.name == name), None)
    if status is None:
        # Naming the available checks rather than a bare "missing": a renamed check would
        # otherwise read as a probe that silently stopped reporting.
        raise AssertionError(
            f"no check named {name!r} in the report. Present: "
            f"{sorted(r.name for r in report.results)}")
    return status


@pytest.mark.slow
def test_the_xss_probe_fails_an_app_that_writes_user_text_with_innerhtml(tmp_path):
    """The gate. A checker that cannot fail a vulnerable app is worse than no checker."""
    base, proc = _serve(tmp_path, "innerHTML")
    try:
        report = _check(base)
    finally:
        proc.kill()

    verdict = _verdict(report, "stored XSS probe")
    assert verdict == "fail", (
        f"the XSS probe did not fail an app that renders a stored payload with innerHTML - "
        f"it said {verdict!r}. Full report: {report.summary()}")


@pytest.mark.slow
def test_the_xss_probe_passes_the_same_app_with_textcontent(tmp_path):
    """The other direction, and the reason the two fixtures differ by one word.

    Without this, a probe that returned "fail" unconditionally would pass the gate above.
    """
    base, proc = _serve(tmp_path, "textContent")
    try:
        report = _check(base)
    finally:
        proc.kill()

    verdict = _verdict(report, "stored XSS probe")
    assert verdict == "pass", (
        f"the XSS probe would not pass a correctly-escaping app - it said {verdict!r}. "
        f"A check that fails everything is as useless as one that passes everything. "
        f"Full report: {report.summary()}")

    # Same run, no extra server: the well-built fixture is also the positive control for
    # every accessibility and layout check, which the defective fixture below inverts.
    for name in ("inputs labelled on /signup", "tap targets >=44px on /signup",
                 "no placeholder values on /dashboard", "no horizontal scroll on /signup"):
        assert _verdict(report, name) == "pass", (
            f"{name!r} failed a correctly-built page: {report.summary()}")


@pytest.mark.slow
def test_every_accessibility_and_layout_check_fails_the_defect_it_exists_to_catch(tmp_path):
    """One fixture carrying every defect, asserted check by check.

    Each of these passed Arm B of the build-off, which is how a page with no labels, no
    focus ring, no tap-target rule and a literal "undefined km" scored full marks on the
    frontend. The checks were added afterwards; this is the part that proves they bite.
    """
    base, proc = _serve(tmp_path, "textContent", DEFECTIVE)
    try:
        report = _check(base)
    finally:
        proc.kill()

    expected_failures = {
        "inputs labelled on /signup": "inputs with no <label for> and no aria-label",
        "tap targets >=44px on /signup": "20px-tall controls",
        "no placeholder values on /dashboard": 'a literal "undefined km" in the page',
        "no horizontal scroll on /signup": "a 2000px-wide element at a 390px viewport",
    }
    survived = {name: _verdict(report, name) for name in expected_failures
                if _verdict(report, name) != "fail"}
    assert not survived, (
        "these checks did not catch the defect they exist for: "
        + "; ".join(f"{n} ({expected_failures[n]}) -> {v}" for n, v in survived.items())
        + f"\nFull report: {report.summary()}")
