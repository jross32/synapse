"""Browser-level checks for a generated app: does it actually work when rendered?

Split into its own module because the original rubric awarded a perfect frontend score to a
build carrying a stored cross-site-scripting hole and a dashboard that rendered nothing. It
checked that pages were *served*. Serving a page proves the HTTP layer works and says nothing
about what a person would see.

Every check here needs a real browser, so when Playwright is unavailable each returns `skip`
and never `pass`. A gate that silently weakens when a dependency is missing still shows a
green tick, which is worse than having no gate at all.
"""

from __future__ import annotations

import time
from typing import Any

XSS_PAYLOAD = '<img src=x onerror="window.__xss_fired=1">'

# Field names differ between builds; try the plausible ones rather than assuming one shape.
CREATE_PATHS = ("/api/records", "/api/trails", "/api/items", "/api/notes")
TITLE_FIELDS = ("title", "name")

DETECT_TOKEN_KEY = r"""() => {
  const src = [...document.querySelectorAll('script')].map(s => s.textContent).join('\n');
  const m = src.match(/localStorage\.(?:get|set)Item\(\s*['"]([^'"]+)/);
  return m ? m[1] : 'app_token';
}"""

SETUP_FLOW = """async (cfg) => {
  const s = await fetch('/api/signup', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({email: cfg.email, password: 'probe-password-123'})});
  const sd = await s.json().catch(() => ({}));
  const tok = sd.token || sd.access_token || sd.session_token;
  if (!tok) return {ok: false, why: 'signup returned no token'};
  let created = false;
  for (const path of cfg.paths) {
    for (const field of cfg.fields) {
      const body = {amount: 1, distance_km: 1, date: '2026-01-01'};
      body[field] = cfg.payload;
      const r = await fetch(path, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok},
        body: JSON.stringify(body)});
      if (r.ok) { created = true; break; }
    }
    if (created) break;
  }
  localStorage.setItem(cfg.key, tok);
  return {ok: created, why: created ? '' : 'could not create a record through any known route'};
}"""

UNLABELLED = """() => [...document.querySelectorAll('input:not([type=hidden])')]
  .filter(el => !el.labels?.length && !el.getAttribute('aria-label'))
  .map(el => el.id || el.name || el.type)"""

SMALL_CONTROLS = """() => [...document.querySelectorAll('button, a.btn, input[type=submit]')]
  .map(el => Math.round(el.getBoundingClientRect().height))
  .filter(h => h > 0 && h < 44)"""


def render_checks(base: str) -> dict[str, Any]:
    """Returns pass / fail / skip per check, with a reason on anything that is not a pass."""
    keys = ("xss", "placeholders", "labels", "mobile")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {k: "skip" for k in keys} | {"xss_detail": "playwright not installed"}

    out: dict[str, Any] = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()

            page.goto(f"{base}/signup", wait_until="networkidle")
            token_key = page.evaluate(DETECT_TOKEN_KEY)

            stamp = str(int(time.time() * 1000))[-8:]
            setup = page.evaluate(SETUP_FLOW, {
                "email": f"probe{stamp}@t.io", "payload": XSS_PAYLOAD, "key": token_key,
                "paths": list(CREATE_PATHS), "fields": list(TITLE_FIELDS)})

            page.goto(f"{base}/dashboard", wait_until="networkidle")
            page.wait_for_timeout(900)

            if not setup.get("ok"):
                out["xss"] = "skip"
                out["xss_detail"] = setup.get("why", "setup failed")
            else:
                fired = page.evaluate("() => !!window.__xss_fired")
                body_text = page.inner_text("body")
                # If the payload never reached the page, "it did not fire" proves nothing.
                appeared = "img src" in body_text or page.evaluate(
                    "() => document.querySelectorAll('img[onerror]').length > 0")
                if fired:
                    out["xss"] = "fail"
                    out["xss_detail"] = "a stored payload executed when rendered"
                elif not appeared:
                    out["xss"] = "skip"
                    out["xss_detail"] = ("the record never rendered, so escaping could not "
                                         "be verified - the view is not showing records")
                else:
                    out["xss"] = "pass"

            text = page.inner_text("body")
            leaked = [v for v in ("undefined", "NaN", "[object Object]") if v in text]
            out["placeholders"] = "fail" if leaked else "pass"
            out["placeholders_detail"] = (f"shows {leaked} - a template read a field that "
                                          f"does not exist" if leaked else "")

            unlabelled: list[str] = []
            for path in ("/signup", "/login"):
                page.goto(f"{base}{path}", wait_until="networkidle")
                unlabelled += page.evaluate(UNLABELLED)
            out["labels"] = "fail" if unlabelled else "pass"
            out["labels_detail"] = f"unlabelled: {unlabelled}" if unlabelled else ""

            small = page.evaluate(SMALL_CONTROLS)
            hscroll = page.evaluate("() => document.documentElement.scrollWidth > "
                                    "document.documentElement.clientWidth + 2")
            out["mobile"] = "fail" if (small or hscroll) else "pass"
            out["mobile_detail"] = (f"{len(small)} controls under 44px" if small else
                                    ("scrolls sideways at 390px" if hscroll else ""))
            browser.close()
    except Exception as exc:  # noqa: BLE001 -- a broken probe must not be read as a pass
        for key in keys:
            out.setdefault(key, "skip")
        out.setdefault("xss_detail", f"{type(exc).__name__}: {exc}")
    return out
