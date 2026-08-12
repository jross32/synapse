"""Score a Trailmark build against SPEC.md. Same rubric for both arms.

Written before either app existed, so the rubric could not be shaped around whatever one
of them happened to produce. Nothing here is a judgement call: the app is started for real,
driven over HTTP, and graded on what it does. A build cannot argue with a 500.

Six categories, 100 points:

    functionality   35   the API does what the spec says
    security        25   auth actually protects data
    robustness      15   bad input is refused, not crashed on
    frontend        15   the four pages exist and carry their controls
    code_quality     5   structure, size, no obvious dead weight
    spec_compliance  5   runs the way the spec requires, with no extra setup

Security is weighted second-heaviest deliberately. A signup form that stores plaintext
passwords is not "mostly working" - it is the failure that matters most, and a rubric that
lets polish outweigh it would be measuring the wrong thing.

    python score_app.py <app-dir> [--port 8099] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import re
import asyncio
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "daemon"))
from synapse_daemon.scaffold import webcheck as webcheck_mod  # noqa: E402

# The frozen spec's shape, so the hostile-input probe posts to a route that exists. A probe
# aimed at the wrong endpoint creates nothing, and a probe that creates nothing proves
# nothing while still appearing in the report as though it had run.
TRAIL_FLOW = {
    "signup": {"path": "/api/signup",
               "body": {"email": "probe@probe.test", "password": "probe-password-123"}},
    "create": {"path": "/api/trails",
               "body": {"name": webcheck_mod.XSS_PAYLOAD, "distance_km": 1.0,
                        "date": "2026-01-01"}},
    "view": "/dashboard",
}
RENDERED_PAGES = ["/", "/signup", "/login", "/dashboard"]


def render_checks(base: str) -> dict[str, str]:
    """Aggregate the real webcheck into the handful of verdicts this rubric scores.

    Previously this rubric used `render_checks.py`, a second implementation of the same
    ideas. Two copies drifted, as two copies do: the scorer's had no notion of "the view
    renders nothing", so the build-off's local arm - whose dashboard reads `data.trails`
    from an endpoint returning a bare array and therefore renders an empty list forever -
    lost no frontend points for it. One implementation, the tested one.
    """
    report = asyncio.run(webcheck_mod.check_app(base, pages=RENDERED_PAGES,
                                                flow=TRAIL_FLOW))

    def rollup(prefix: str) -> tuple[str, str]:
        hits = [r for r in report.results if r.name.startswith(prefix)]
        if not hits:
            return "not_run", "the check did not run"
        bad = [r for r in hits if r.status == "fail"]
        if bad:
            return "fail", "; ".join(f"{r.name}: {r.detail}" for r in bad[:2])
        return ("pass", "") if all(r.status == "pass" for r in hits) else (
            "not_run", "; ".join(r.detail for r in hits if r.status == "not_run")[:200])

    named = {r.name: r for r in report.results}
    out: dict[str, str] = {}
    for key, source in (("xss", "stored XSS probe"),
                        ("records", "records render in the view")):
        hit = named.get(source)
        out[key] = hit.status if hit else "not_run"
        out[f"{key}_detail"] = hit.detail if hit else "the check did not run"
    for key, prefix in (("placeholders", "no placeholder values"),
                        ("labels", "inputs labelled"),
                        ("mobile", "tap targets")):
        out[key], out[f"{key}_detail"] = rollup(prefix)
    scroll, scroll_detail = rollup("no horizontal scroll")
    if scroll == "fail":
        out["mobile"], out["mobile_detail"] = "fail", scroll_detail
    return out


class Result:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, category: str, name: str, points: float, max_points: float,
            detail: str = "") -> None:
        self.checks.append({"category": category, "name": name, "points": points,
                            "max": max_points, "detail": detail})
        mark = "PASS" if points >= max_points else ("PART" if points > 0 else "FAIL")
        print(f"  {category:16s} {name:34s} {mark} {points:4.1f}/{max_points:<4.1f} {detail[:60]}")

    def totals(self) -> dict[str, Any]:
        cats: dict[str, dict[str, float]] = {}
        for c in self.checks:
            slot = cats.setdefault(c["category"], {"points": 0.0, "max": 0.0})
            slot["points"] += c["points"]
            slot["max"] += c["max"]
        total = sum(v["points"] for v in cats.values())
        mx = sum(v["max"] for v in cats.values())
        return {"categories": cats, "total": round(total, 1), "max": round(mx, 1),
                "percent": round(100 * total / mx, 1) if mx else 0.0}


# ------------------------------------------------------------------ http helpers


def req(method: str, url: str, body: dict | None = None, token: str | None = None,
        timeout: float = 10.0) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def token_from(payload: Any) -> str | None:
    """Accept any sensible field name - the spec says 'a session token', not which key."""
    if not isinstance(payload, dict):
        return None
    for k in ("token", "session_token", "access_token", "sessionToken", "jwt", "id"):
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
    for v in payload.values():
        if isinstance(v, dict):
            got = token_from(v)
            if got:
                return got
    return None


def wait_for_port(port: int, timeout: float = 45.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(1.0)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


# ------------------------------------------------------------------ the checks


def score(app_dir: Path, port: int) -> tuple[Result, dict[str, Any]]:
    res = Result()
    base = f"http://127.0.0.1:{port}"
    entry = app_dir / "app.py"

    # -- spec compliance: does it start the way the spec demands, with nothing else? ----
    proc = None
    started = False
    if not entry.exists():
        res.add("spec_compliance", "app.py exists", 0, 2, "no app.py")
        # Still record the start check, at zero. Skipping it would shrink the denominator
        # and make a failed build score out of 97 while a working one scores out of 100 -
        # the two numbers would not be comparable, which defeats the point.
        res.add("spec_compliance", "starts with no extra setup", 0, 3, "no app.py to start")
    else:
        res.add("spec_compliance", "app.py exists", 2, 2)
        proc = subprocess.Popen([sys.executable, "app.py", "--port", str(port)],
                                cwd=str(app_dir), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        started = wait_for_port(port)
        res.add("spec_compliance", "starts with no extra setup", 3 if started else 0, 3,
                "" if started else "never bound the port")

    if not started:
        # Everything else needs a live server; report honestly rather than inventing zeros
        # with no explanation.
        for cat, mx in (("functionality", 35), ("security", 25), ("robustness", 15),
                        ("frontend", 15)):
            res.add(cat, "server never started", 0, mx, "app did not run")
        res.add("code_quality", "not assessed", 0, 5, "app did not run")
        if proc:
            proc.terminate()
        return res, {"started": False}

    try:
        # -- functionality ------------------------------------------------------------
        st, health = req("GET", f"{base}/api/health")
        ok_health = st == 200 and isinstance(health, dict) and health.get("status") == "ok"
        res.add("functionality", "GET /api/health", 3 if ok_health else 0, 3, f"status {st}")

        stamp = str(int(time.time() * 1000))[-8:]
        u1 = {"email": f"a{stamp}@t.io", "password": "pw-alpha-12345"}
        u2 = {"email": f"b{stamp}@t.io", "password": "pw-bravo-12345"}

        st, body = req("POST", f"{base}/api/signup", u1)
        t1 = token_from(body)
        res.add("functionality", "POST /api/signup returns token",
                5 if (st in (200, 201) and t1) else 0, 5, f"status {st}")

        st_dup, _ = req("POST", f"{base}/api/signup", u1)
        res.add("functionality", "duplicate signup refused",
                4 if 400 <= st_dup < 500 else 0, 4, f"status {st_dup}")

        st, body = req("POST", f"{base}/api/login", u1)
        t1 = token_from(body) or t1
        res.add("functionality", "POST /api/login returns token",
                5 if (st == 200 and t1) else 0, 5, f"status {st}")

        st_bad, _ = req("POST", f"{base}/api/login",
                        {"email": u1["email"], "password": "wrong-password"})
        res.add("functionality", "wrong password refused",
                4 if 400 <= st_bad < 500 else 0, 4, f"status {st_bad}")

        st, trails = req("GET", f"{base}/api/trails", token=t1)
        empty_ok = st == 200 and isinstance(trails, list) and len(trails) == 0
        res.add("functionality", "GET /api/trails starts empty",
                3 if empty_ok else 0, 3, f"status {st}")

        st, made = req("POST", f"{base}/api/trails",
                       {"name": "Ridge Loop", "distance_km": 12.5, "date": "2026-05-02"},
                       token=t1)
        created_ok = st in (200, 201)
        res.add("functionality", "POST /api/trails creates",
                5 if created_ok else 0, 5, f"status {st}")

        st, trails = req("GET", f"{base}/api/trails", token=t1)
        listed = isinstance(trails, list) and len(trails) == 1
        res.add("functionality", "created trail is listed",
                3 if listed else 0, 3, f"{len(trails) if isinstance(trails, list) else '?'} rows")

        trail_id = None
        if isinstance(trails, list) and trails:
            trail_id = trails[0].get("id") if isinstance(trails[0], dict) else None
        st_del, _ = req("DELETE", f"{base}/api/trails/{trail_id}", token=t1)
        st, after = req("GET", f"{base}/api/trails", token=t1)
        deleted = st_del in (200, 204) and isinstance(after, list) and not after
        res.add("functionality", "DELETE /api/trails/{id}", 3 if deleted else 0, 3,
                f"status {st_del}")

        # -- security -----------------------------------------------------------------
        st_anon, _ = req("GET", f"{base}/api/trails")
        res.add("security", "trails require auth (401)",
                8 if st_anon == 401 else (3 if 400 <= st_anon < 500 else 0), 8,
                f"status {st_anon}")

        st_bogus, _ = req("GET", f"{base}/api/trails", token="not-a-real-token")
        res.add("security", "forged token rejected",
                5 if 400 <= st_bogus < 500 else 0, 5, f"status {st_bogus}")

        # cross-tenant: user 2 must not see or delete user 1's row
        req("POST", f"{base}/api/signup", u2)
        st, body = req("POST", f"{base}/api/login", u2)
        t2 = token_from(body)
        req("POST", f"{base}/api/trails",
            {"name": "Private Path", "distance_km": 3.0, "date": "2026-05-03"}, token=t1)
        _, mine = req("GET", f"{base}/api/trails", token=t1)
        _, theirs = req("GET", f"{base}/api/trails", token=t2)
        isolated = isinstance(theirs, list) and len(theirs) == 0 and isinstance(mine, list) and mine
        res.add("security", "users cannot read each other's trails",
                7 if isolated else 0, 7,
                f"other user saw {len(theirs) if isinstance(theirs, list) else '?'}")

        other_id = mine[0].get("id") if isinstance(mine, list) and mine and isinstance(mine[0], dict) else None
        st_x, _ = req("DELETE", f"{base}/api/trails/{other_id}", token=t2)
        _, still = req("GET", f"{base}/api/trails", token=t1)
        blocked = st_x in (401, 403, 404) and isinstance(still, list) and len(still) >= 1
        res.add("security", "cannot delete another user's trail",
                5 if blocked else 0, 5, f"status {st_x}")

        # passwords must not be recoverable from disk
        plaintext = []
        for f in list(app_dir.rglob("*.db")) + list(app_dir.rglob("*.sqlite*")) + \
                 list(app_dir.rglob("*.json")):
            try:
                blob = f.read_bytes()
            except Exception:  # noqa: BLE001
                continue
            if b"pw-alpha-12345" in blob or b"pw-bravo-12345" in blob:
                plaintext.append(f.name)
        res.add("security", "passwords not stored in plain text",
                0 if plaintext else 5, 5,
                f"found in {plaintext}" if plaintext else "")

        # -- robustness ---------------------------------------------------------------
        cases = [
            ("signup missing password", "POST", "/api/signup", {"email": "x@y.io"}, None),
            ("signup empty body", "POST", "/api/signup", {}, None),
            ("login missing fields", "POST", "/api/login", {}, None),
            ("trail missing name", "POST", "/api/trails", {"distance_km": 1}, "T1"),
            ("trail bad distance type", "POST", "/api/trails",
             {"name": "x", "distance_km": "not-a-number", "date": "2026-01-01"}, "T1"),
            ("delete non-existent trail", "DELETE", "/api/trails/999999", None, "T1"),
        ]
        for name, method, path, body, who in cases:
            tok = t1 if who == "T1" else None
            st_c, _ = req(method, f"{base}{path}", body, token=tok)
            good = 400 <= st_c < 500
            res.add("robustness", name, 2.5 if good else 0, 2.5,
                    f"status {st_c}" + (" (5xx = crash)" if st_c >= 500 else ""))

        # -- frontend ------------------------------------------------------------------
        # Being served is worth only 4 of the 15 now. The original rubric gave full marks
        # here to a build with a stored XSS hole and a dashboard that rendered nothing,
        # because it never opened a browser - it was measuring HTTP, not the frontend.
        pages = {"/": ["sign", "log"], "/signup": ["email", "password"],
                 "/login": ["email", "password"], "/dashboard": []}
        served_ok = 0
        for path, needles in pages.items():
            st_p, html = req("GET", f"{base}{path}")
            served = st_p == 200 and isinstance(html, str) and len(html) > 200
            if served and all(n in html.lower() for n in needles):
                served_ok += 1
        res.add("frontend", "all four pages served", served_ok * 0.75, 3, f"{served_ok}/4")

        render = render_checks(base)
        res.add("frontend", "user text is escaped (stored XSS)",
                4 if render.get("xss") == "pass" else 0, 4, render.get("xss_detail", ""))
        # Worth as much as being served. An app whose list view never shows what the user
        # just created is not partly working - and every other check on this page passes,
        # because an empty page has nothing wrong with it to find.
        res.add("frontend", "records render in the view",
                3 if render.get("records") == "pass" else 0, 3,
                render.get("records_detail", ""))
        res.add("frontend", "no placeholder values on screen",
                2 if render.get("placeholders") == "pass" else 0, 2,
                render.get("placeholders_detail", ""))
        res.add("frontend", "every input has a label",
                2 if render.get("labels") == "pass" else 0, 2,
                render.get("labels_detail", ""))
        res.add("frontend", "44px controls, fits 390px",
                1 if render.get("mobile") == "pass" else 0, 1,
                render.get("mobile_detail", ""))

        # -- code quality ---------------------------------------------------------------
        py = list(app_dir.rglob("*.py"))
        total_lines = sum(len(p.read_text(encoding="utf-8", errors="replace").splitlines())
                          for p in py)
        organised = 40 <= total_lines <= 1200
        res.add("code_quality", "reasonable size", 2 if organised else 1, 2,
                f"{total_lines} lines of python")
        src = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in py)
        hashed = bool(re.search(r"hashlib|bcrypt|scrypt|pbkdf2|argon", src, re.I))
        res.add("code_quality", "uses a real hashing primitive", 2 if hashed else 0, 2)
        has_docs = bool(re.search(r'"""', src))
        res.add("code_quality", "has docstrings", 1 if has_docs else 0, 1)

    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    return res, {"started": True}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("app_dir")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    app_dir = Path(args.app_dir).resolve()
    print(f"\n=== scoring {app_dir.name} ===")
    res, meta = score(app_dir, args.port)
    totals = res.totals()

    print(f"\n  {'category':18s} {'score':>12s}")
    for cat, v in sorted(totals["categories"].items()):
        print(f"  {cat:18s} {v['points']:6.1f}/{v['max']:<5.1f}")
    print(f"  {'TOTAL':18s} {totals['total']:6.1f}/{totals['max']:<5.1f}  = {totals['percent']}%")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"app": app_dir.name, "totals": totals, "checks": res.checks, **meta},
            indent=1), encoding="utf-8")
        print(f"\n  json -> {args.json}")


if __name__ == "__main__":
    main()
