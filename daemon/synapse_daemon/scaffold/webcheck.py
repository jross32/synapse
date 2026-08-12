"""Render a generated app, attack it, and report what a rubric that only speaks HTTP misses.

This exists because of a specific failure. In the build-off, an app scored 15/15 on frontend
while shipping a stored XSS hole and a dashboard that rendered "undefined km" on every row.
The rubric checked that pages were *served*; it never checked that they *worked*. Both defects
were found afterwards, by hand.

So these checks run inside the build loop instead, where a failure becomes a free local repair
cycle rather than something a human has to notice later.

Two sources, deliberately:

* The **web-scraper** (already running on :12345) does broken links, security-header grading
  and full-page scraping. Those are solved problems with rate limiting and concurrency already
  handled; reimplementing them would be worse and slower.
* **Playwright** does what the scraper cannot: execute a hostile payload and see whether it
  fired, read computed styles for tap targets and focus rings, and scan *rendered* text for
  values that leaked through as ``undefined``.

If the scraper is not reachable, its checks report ``not_run`` — never ``pass``. A gate that
quietly weakens when a dependency is missing is worse than no gate, because it still produces
a green tick.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

SCRAPER = "http://127.0.0.1:12345"

# Values that mean "a template rendered something it should not have". `undefined` is the one
# that shipped; the rest are the same mistake wearing different clothes.
LEAKED_VALUES = ("undefined", "NaN", "[object Object]", "null km", "None")

# Fires only if the payload is inserted as markup rather than text.
XSS_PAYLOAD = '<img src=x onerror="window.__xss_fired=1">'


@dataclass
class CheckResult:
    name: str
    status: str            # pass | fail | not_run
    detail: str = ""
    source: str = "webcheck"

    @property
    def ok(self) -> bool:
        return self.status == "pass"


@dataclass
class WebCheckReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "", source: str = "webcheck") -> None:
        self.results.append(CheckResult(name, status, detail, source))

    @property
    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == "fail"]

    @property
    def not_run(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == "not_run"]

    @property
    def passed(self) -> bool:
        return not self.failures

    def as_repair_text(self) -> str:
        """Failures phrased so a model can act on them, which is the whole point."""
        if not self.failures:
            return ""
        lines = ["The application was rendered in a browser and these checks failed:"]
        for r in self.failures:
            lines.append(f"- {r.name}: {r.detail}")
        return "\n".join(lines)

    def summary(self) -> str:
        p = sum(1 for r in self.results if r.status == "pass")
        return (f"{p}/{len(self.results)} passed, {len(self.failures)} failed, "
                f"{len(self.not_run)} not run")


# ---------------------------------------------------------------- web-scraper checks


def _scraper_post(path: str, payload: dict[str, Any], timeout: float = 60.0) -> Any:
    req = urllib.request.Request(
        f"{SCRAPER}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def scraper_available(timeout: float = 3.0) -> bool:
    try:
        urllib.request.urlopen(f"{SCRAPER}/", timeout=timeout).read(1)
        return True
    except Exception:  # noqa: BLE001
        return False


def _wait_for_scrape(session_id: str, timeout: float = 90.0) -> bool:
    """Scraping is asynchronous; poll until the save exists or we give up."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{SCRAPER}/api/scrape/{session_id}", method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace"))
            if body.get("status") in ("complete", "completed", "done") or body.get("pages"):
                return True
        except Exception:  # noqa: BLE001 -- not ready yet
            pass
        time.sleep(2.0)
    return False


def run_scraper_checks(base_url: str, report: WebCheckReport) -> None:
    """Delegate to the web-scraper what it already does better than a reimplementation.

    Both endpoints work off a saved scrape rather than a bare URL, so the site is scraped
    once and that save feeds both checks.
    """
    if not scraper_available():
        for name in ("security headers", "broken links"):
            report.add(name, "not_run",
                       "web-scraper not reachable on :12345 - skipped, NOT passed",
                       source="web-scraper")
        return

    session_id = ""
    try:
        started = _scraper_post("/api/scrape", {"url": base_url, "maxPages": 4})
        session_id = started.get("sessionId", "")
        if session_id and not _wait_for_scrape(session_id):
            session_id = ""
    except Exception as exc:  # noqa: BLE001
        report.add("broken links", "not_run", f"scrape failed: {type(exc).__name__}: {exc}",
                   source="web-scraper")

    # Security headers can be graded from the live response directly, so this check does not
    # depend on the scrape succeeding.
    try:
        with urllib.request.urlopen(base_url, timeout=15) as resp:
            live_headers = {k: v for k, v in resp.headers.items()}
        data = _scraper_post("/api/security-score", {"securityHeaders": live_headers})
        grade = data.get("grade") or data.get("score")
        recs = data.get("recommendations") or []
        high = [r for r in recs
                if str(r.get("priority", "")).lower() in ("high", "critical")]
        report.add("security headers", "fail" if high else "pass",
                   f"grade {grade}"
                   + (f"; missing: {[r.get('header') for r in high][:4]}" if high else ""),
                   source="web-scraper")
    except Exception as exc:  # noqa: BLE001
        report.add("security headers", "not_run", f"{type(exc).__name__}: {exc}",
                   source="web-scraper")

    if not session_id:
        report.add("broken links", "not_run", "no completed scrape to check against",
                   source="web-scraper")
        return
    try:
        data = _scraper_post("/api/broken-links",
                             {"sessionId": session_id, "internalOnly": True})
        broken = data.get("broken") or []
        report.add("broken links", "fail" if broken else "pass",
                   f"{len(broken)} broken: {[b.get('url') for b in broken[:3]]}"
                   if broken else f"{data.get('ok', 0)} links ok",
                   source="web-scraper")
    except Exception as exc:  # noqa: BLE001
        report.add("broken links", "not_run", f"{type(exc).__name__}: {exc}",
                   source="web-scraper")


# ---------------------------------------------------------------- browser checks


async def run_browser_checks(base_url: str, report: WebCheckReport,
                             pages: list[str], flow: dict[str, Any] | None = None) -> None:
    """Render each page and inspect what actually reached the screen."""
    try:
        from playwright.async_api import async_playwright  # noqa: PLC0415
    except ImportError:
        report.add("browser checks", "not_run", "playwright not installed — NOT passed")
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            ctx = await browser.new_context(viewport={"width": 390, "height": 844})
            page = await ctx.new_page()
            console_errors: list[str] = []
            page.on("console", lambda m: console_errors.append(m.text)
                    if m.type == "error" else None)
            # A thrown exception never reaches the console listener, and an uncaught
            # TypeError is the single most likely reason a view renders nothing.
            page.on("pageerror", lambda e: console_errors.append(f"uncaught: {e}"))

            # Sign in before inspecting anything. Running the page checks first meant every
            # authenticated view was graded as the login page it redirects to: against Arm B
            # the dashboard was reported as having two unlabelled controls (they were the
            # login form's) and no console errors (its own JavaScript throws on load, but
            # that code never ran). A check pointed at the wrong page cannot fail correctly.
            setup_failure = ""
            if flow:
                setup_failure = await _setup_flow(page, base_url, flow, report)

            for path in pages:
                await page.goto(f"{base_url}{path}", wait_until="networkidle")

                # Values that leaked through a template rather than being rendered.
                text = await page.inner_text("body")
                leaked = [v for v in LEAKED_VALUES if v in text]
                report.add(f"no placeholder values on {path}",
                           "fail" if leaked else "pass",
                           f"page shows {leaked} in its rendered text — a template read a "
                           f"field that does not exist" if leaked else "")

                # Every input needs a programmatic label.
                unlabelled = await page.evaluate("""() => {
                  return [...document.querySelectorAll('input:not([type=hidden]),select,textarea')]
                    .filter(el => !el.labels?.length && !el.getAttribute('aria-label'))
                    .map(el => el.id || el.name || el.type);
                }""")
                report.add(f"inputs labelled on {path}",
                           "fail" if unlabelled else "pass",
                           f"unlabelled controls: {unlabelled}" if unlabelled else "")

                # Touch targets.
                small = await page.evaluate("""() => {
                  return [...document.querySelectorAll('button,a.btn,input[type=submit]')]
                    .map(el => ({ t: (el.textContent||el.value||'').trim().slice(0,20),
                                  h: Math.round(el.getBoundingClientRect().height) }))
                    .filter(x => x.h > 0 && x.h < 44);
                }""")
                report.add(f"tap targets >=44px on {path}",
                           "fail" if small else "pass",
                           f"too small: {small}" if small else "")

                # Horizontal overflow at phone width.
                hscroll = await page.evaluate(
                    "() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
                report.add(f"no horizontal scroll on {path}",
                           "fail" if hscroll else "pass",
                           "page scrolls sideways at 390px" if hscroll else "")

            report.add("no console errors", "fail" if console_errors else "pass",
                       "; ".join(console_errors[:3]) if console_errors else "")

            if flow:
                await _xss_verdict(page, base_url, flow, report, setup_failure)
        finally:
            await browser.close()


async def _detect_token_key(page: Any, base_url: str, view: str) -> str:
    """Read the app's own localStorage key out of its served JavaScript.

    Assuming a key name is how the first version of this probe reported a pass against a
    genuinely vulnerable app: the wrong key meant the dashboard bounced to /login and the
    payload never rendered.
    """
    try:
        await page.goto(f"{base_url}{view}", wait_until="domcontentloaded")
        # No newline escape anywhere in this snippet. The previous version joined on '\n'
        # written as a real line break inside a JS string literal, which is a syntax error;
        # page.evaluate threw, the except below swallowed it, and the function returned its
        # fallback every single time it was ever called. It looked like detection and was a
        # hardcoded constant - the exact assumption its own docstring warns against.
        found = await page.evaluate(
            r"""() => {
              const parts = [...document.querySelectorAll('script')].map(s => s.textContent);
              const re = /localStorage\.(?:get|set)Item\(\s*['"]([^'"]+)/;
              for (const src of parts) {
                const m = (src || '').match(re);
                if (m) return m[1];
              }
              return '';
            }""")
        # Empty when nothing was found, so the caller can tell "the app says nothing" from
        # "the app says app_token". Returning a plausible default here made detection look
        # authoritative when it had in fact failed.
        return found or ""
    except Exception:  # noqa: BLE001
        return ""


def _unique_email(template: str) -> str:
    """A fresh account per run.

    The flow declares a fixed address, which works exactly once: every later run against the
    same database gets 409 and the probe reports `not_run`. Since a build is normally graded
    repeatedly, a fixed address means the hostile-input check is skipped nearly every time it
    matters, while still appearing in the report as though it had been considered.
    """
    # Random rather than clock-derived: Windows' timer granularity is coarse enough that two
    # consecutive time_ns() calls return the same value, which is exactly the collision this
    # function exists to avoid.
    stamp = secrets.token_hex(5)
    local, _, domain = template.partition("@")
    return f"{local}+{stamp}@{domain or 'probe.test'}"


async def _setup_flow(page: Any, base_url: str, flow: dict[str, Any],
                      report: WebCheckReport) -> str:
    """Sign up, store a hostile record, and authenticate the browser.

    Returns "" on success or the reason it could not be done. Split from the verdict so the
    page checks in between run against a signed-in session.
    """
    try:
        signup = flow["signup"]          # {"path": "/api/signup", "body": {...}}
        create = flow["create"]          # {"path": "/api/trails", "body": {...}, "field": "name"}
        view = flow.get("view", "/dashboard")

        # Detection wins over configuration, not the other way round. The docstring on
        # _detect_token_key records that assuming a key is how this probe first produced a
        # false pass, and taking `flow["token_key"]` in preference to detection walked
        # straight back into it: against Arm B the configured `app_token` left the browser
        # unauthenticated, the dashboard served its login page instead, and the run came back
        # with "no console errors: pass" for a view whose JavaScript throws on every load.
        # What the app's own served script says is evidence; what the flow says is a guess
        # written before the app existed, so it is only the fallback.
        detected = await _detect_token_key(page, base_url, view)
        configured = flow.get("token_key") or ""
        token_key = detected or configured or "app_token"
        if configured and detected and configured != detected:
            report.add("token key", "pass",
                       f"the app stores its token as {detected!r}; the flow said "
                       f"{configured!r}. Used the detected one.")

        result = await page.evaluate(
            """async (cfg) => {
              const s = await fetch(cfg.signupPath, {method:'POST',
                headers:{'Content-Type':'application/json'}, body: JSON.stringify(cfg.signupBody)});
              const sd = await s.json().catch(() => ({}));
              const token = sd.token || sd.access_token || sd.session_token;
              if (!token) return { ok:false, why:'signup returned no token: ' + JSON.stringify(sd).slice(0,120) };
              const c = await fetch(cfg.createPath, {method:'POST',
                headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},
                body: JSON.stringify(cfg.createBody)});
              if (!c.ok) return { ok:false, why:'create failed ' + c.status };
              localStorage.setItem(cfg.tokenKey, token);
              return { ok:true };
            }""",
            {"signupPath": f"{base_url}{signup['path']}",
             "signupBody": dict(signup["body"],
                                email=_unique_email(signup["body"].get("email",
                                                                      "probe@probe.test"))),
             "createPath": f"{base_url}{create['path']}", "createBody": create["body"],
             "tokenKey": token_key},
        )
        return "" if result.get("ok") else str(result.get("why", "setup failed"))
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


async def _xss_verdict(page: Any, base_url: str, flow: dict[str, Any],
                       report: WebCheckReport, setup_failure: str) -> None:
    """Did the stored payload execute, and did the record render at all?

    This is the check that would have caught Arm B. It does not inspect source for
    ``innerHTML`` — plenty of safe code uses it — it stores a payload and asks the browser
    whether script ran.
    """
    view = flow.get("view", "/dashboard")
    if setup_failure:
        report.add("stored XSS probe", "not_run", setup_failure)
        report.add("records render in the view", "not_run", setup_failure)
        return
    try:
        await page.goto(f"{base_url}{view}", wait_until="networkidle")
        await page.wait_for_timeout(900)
        fired = await page.evaluate("() => !!window.__xss_fired")

        if fired:
            report.add(
                "stored XSS probe", "fail",
                "a record named with an <img onerror> payload EXECUTED when rendered — user "
                "content is being written as markup instead of text. Escape it, or assign "
                "textContent instead of innerHTML.")
            # It executed, so it certainly rendered. Recorded rather than skipped, so every
            # path through this function leaves both checks with a verdict - a check that is
            # simply absent from the report is indistinguishable from one that passed.
            report.add("records render in the view", "pass",
                       "the stored record reached the page (it executed)")
            return

        # Not firing is only good news if the record actually rendered. If the view is
        # broken and shows nothing, the payload was never given the chance to run, and
        # calling that a pass is a false green - which is exactly what this probe did on its
        # first outing against a genuinely vulnerable app.
        rendered = await page.evaluate(
            """() => {
              const body = document.body.innerText || '';
              const imgs = document.querySelectorAll('img[src="x"], img[onerror]').length;
              return { chars: body.trim().length, imgs,
                       hasRow: !!document.querySelector('[class*=list],[class*=trail],li,tr') };
            }""")
        if rendered["imgs"] == 0 and not rendered["hasRow"]:
            report.add(
                "stored XSS probe", "not_run",
                "the record was created through the API but nothing rendered on "
                f"{view}, so escaping could not be verified. The view is not displaying "
                "records at all — fix that first, then this check becomes meaningful.")
            # Reported separately, and as a failure, because it *is* one. The build-off's
            # local arm shipped a dashboard that read `data.trails` from an endpoint
            # returning a bare array, so `.length` threw and the list stayed empty forever.
            # Every check in the suite was satisfied by that page: no placeholder text, no
            # unlabelled input, nothing to see because nothing rendered. An empty view is
            # the most complete failure a CRUD app has and it was the one thing nothing
            # looked for.
            report.add(
                "records render in the view", "fail",
                f"a record was created through the API and {view} shows no sign of it. "
                "Check what the list endpoint returns against what the page reads from it "
                "— a bare array indexed as if it were an object is the usual cause.")
        else:
            report.add("stored XSS probe", "pass",
                       "hostile payload rendered inertly (escaped)")
            report.add("records render in the view", "pass",
                       "a record created through the API appears on the page")
    except Exception as exc:  # noqa: BLE001
        report.add("stored XSS probe", "not_run", f"{type(exc).__name__}: {exc}")
        report.add("records render in the view", "not_run", f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- entry point


async def check_app(base_url: str, *, pages: list[str] | None = None,
                    flow: dict[str, Any] | None = None) -> WebCheckReport:
    report = WebCheckReport()
    pages = pages or ["/"]
    await run_browser_checks(base_url, report, pages, flow)
    await asyncio.to_thread(run_scraper_checks, base_url, report)
    return report


def default_flow(name_field: str = "name") -> dict[str, Any]:
    """A signup-then-create flow carrying the XSS payload, for the common CRUD shape."""
    stamp = "xss" + str(abs(hash(XSS_PAYLOAD)) % 100000)
    return {
        "token_key": "app_token",
        "signup": {"path": "/api/signup",
                   "body": {"email": f"{stamp}@probe.test", "password": "probe-password-123"}},
        "create": {"path": "/api/trails",
                   "body": {name_field: XSS_PAYLOAD, "distance_km": 1.0, "date": "2026-01-01"}},
        "view": "/dashboard",
    }
