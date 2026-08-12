"""Drive the local models through Trailmark, piece by piece.

Each piece carries its own acceptance test, written here rather than by the model, so a
piece cannot pass by lowering the bar. The tests are the same behaviours SPEC.md demands.
"""

from __future__ import annotations

import time
from pathlib import Path

from build import HERE, LOG, build_piece, save_log

STARTED = time.time()

# ---------------------------------------------------------------- piece 1: passwords

PW_SPEC = """Write a Python module with exactly two functions and no framework imports:

    hash_password(password: str) -> str
    verify_password(password: str, stored: str) -> bool

Requirements:
- Use hashlib.pbkdf2_hmac with sha256, 200000 iterations, and a random 16-byte salt from
  the secrets module.
- hash_password returns a single string containing the algorithm name, the iteration
  count, the salt as hex, and the digest as hex, separated by "$".
- verify_password parses that string, recomputes the digest, and compares using
  hmac.compare_digest. It must return False (never raise) if the stored string is
  malformed, empty, or in an unknown format.
- Two calls to hash_password with the same password must return different strings,
  because the salt is random."""

PW_TEST = """
from passwords import hash_password, verify_password
h = hash_password("correct horse battery")
assert isinstance(h, str) and "$" in h
assert "correct horse battery" not in h, "password must not appear in the hash"
assert verify_password("correct horse battery", h) is True
assert verify_password("wrong", h) is False
assert hash_password("x") != hash_password("x"), "salt must be random"
for junk in ["", "garbage", "a$b$c$d", "pbkdf2_sha256$notanint$aa$bb", None]:
    try:
        assert verify_password("x", junk) is False
    except Exception as e:
        raise AssertionError(f"verify_password raised on {junk!r}: {e}")
print("OK")
"""

# ---------------------------------------------------------------- piece 2: storage

DB_SPEC = """Write a Python module using only sqlite3, secrets, hashlib and time that
implements storage for a trail-logging app. It must define:

    DB_PATH: a module-level pathlib.Path pointing at "trailmark.db" next to this file
    init_db() -> None
    create_user(email: str, password_hash: str) -> int      # returns new user id
    get_user_by_email(email: str) -> dict | None
    create_session(user_id: int) -> str                     # returns a random token
    user_id_for_token(token: str) -> int | None
    delete_session(token: str) -> None
    add_trail(user_id: int, name: str, distance_km: float, date: str) -> dict
    list_trails(user_id: int) -> list[dict]
    delete_trail(trail_id: int, user_id: int) -> bool       # False if not that user's

Requirements:
- Three tables: users (id, email unique, password_hash, created_at),
  sessions (token_hash primary key, user_id, created_at),
  trails (id, user_id, name, distance_km, date, created_at).
- The session token returned by create_session must be random (use secrets.token_urlsafe)
  and only its sha256 hash is stored, never the token itself.
- list_trails and delete_trail must filter by user_id in the SQL statement, so one user
  can never see or delete another user's trails.
- add_trail returns a dict with keys id, name, distance_km, date.
- list_trails returns a list of dicts with those same keys.
- create_user must raise ValueError if the email already exists.
- Every function opens and closes its own connection."""

DB_TEST = """
import os, pathlib
p = pathlib.Path(__file__).parent / "trailmark.db"
if p.exists(): p.unlink()
import storage
storage.init_db()
uid = storage.create_user("a@b.io", "hash-1")
assert isinstance(uid, int)
assert storage.get_user_by_email("a@b.io")["password_hash"] == "hash-1"
assert storage.get_user_by_email("nope@b.io") is None
try:
    storage.create_user("a@b.io", "hash-2"); raise SystemExit("duplicate email must raise")
except ValueError: pass

tok = storage.create_session(uid)
assert isinstance(tok, str) and len(tok) > 20
assert storage.user_id_for_token(tok) == uid
assert storage.user_id_for_token("bogus") is None

t = storage.add_trail(uid, "Ridge", 12.5, "2026-05-02")
assert t["id"] and t["name"] == "Ridge" and t["distance_km"] == 12.5 and t["date"] == "2026-05-02"
rows = storage.list_trails(uid)
assert len(rows) == 1 and rows[0]["name"] == "Ridge"

other = storage.create_user("c@d.io", "hash-3")
assert storage.list_trails(other) == [], "users must not see each other's trails"
assert storage.delete_trail(t["id"], other) is False, "must not delete another user's trail"
assert len(storage.list_trails(uid)) == 1
assert storage.delete_trail(t["id"], uid) is True
assert storage.list_trails(uid) == []

storage.delete_session(tok)
assert storage.user_id_for_token(tok) is None
print("OK")
"""

# ---------------------------------------------------------------- piece 3: html

HTML_SPEC = """Write a Python module that returns HTML pages for a trail-logging app
called Trailmark. It must define exactly these four functions, each returning a complete
HTML document as a string:

    landing_page() -> str
    signup_page() -> str
    login_page() -> str
    dashboard_page() -> str

Requirements for every page:
- A full document: <!doctype html>, <html lang="en">, <head> with
  <meta name="viewport" content="width=device-width,initial-scale=1">, a <title>, and a
  <style> block with CSS. Dark theme, readable at 375px wide.
- Buttons and inputs must be at least 44px tall for use on a phone.

Page specifics:
- landing_page: an <h1>, a sentence of description, and links to /signup and /login.
- signup_page: a <form> with an email input and an <input type="password">, a submit
  button, and an empty <div id="msg"></div> for errors. Inline JavaScript posts JSON
  {email, password} to /api/signup, stores the returned token in
  localStorage under "tm_token", and redirects to /dashboard. On failure it shows the
  server's error text in #msg.
- login_page: the same but posting to /api/login.
- dashboard_page: a form with inputs for trail name, distance (number) and date, plus a
  <div id="list"></div>. Inline JavaScript reads the token from localStorage, redirects to
  /login if missing, and sends it as an "Authorization: Bearer <token>" header. It loads
  GET /api/trails and renders them with a Delete button each, posts new trails to
  POST /api/trails, and deletes via DELETE /api/trails/{id}. Show a friendly empty state
  when there are no trails.

Output only the Python module."""

HTML_TEST = """
import pages
for fn in ("landing_page", "signup_page", "login_page", "dashboard_page"):
    html = getattr(pages, fn)()
    assert isinstance(html, str) and len(html) > 300, fn
    low = html.lower()
    assert "<!doctype html" in low, fn
    assert "viewport" in low, fn
    assert "<style" in low, fn
assert 'type="password"' in pages.signup_page().lower().replace("'", '"')
assert 'type="password"' in pages.login_page().lower().replace("'", '"')
low = pages.landing_page().lower()
assert "/signup" in low and "/login" in low
d = pages.dashboard_page().lower()
assert "/api/trails" in d and "tm_token" in d and "bearer" in d
s = pages.signup_page().lower()
assert "/api/signup" in s and 'id="msg"' in s.replace("'", '"')
print("OK")
"""

# ---------------------------------------------------------------- piece 4: api

API_SPEC = """Write a FastAPI application module for a trail-logging app.

It must import from two local modules that already exist and work:
    from passwords import hash_password, verify_password
    import storage
    import pages

Define `app = FastAPI()` and these routes:

    GET    /api/health          -> {"status": "ok"}
    POST   /api/signup          -> body {email, password}; 409 if the email exists;
                                   otherwise create the user and return {"token": ...} with
                                   status code 201
    POST   /api/login           -> body {email, password}; 401 if the email is unknown or
                                   the password is wrong; otherwise {"token": ...}
    POST   /api/logout          -> ends the session, returns {"ok": true}
    GET    /api/trails          -> the caller's trails as a list
    POST   /api/trails          -> body {name, distance_km, date}; creates one, status 201
    DELETE /api/trails/{id}     -> deletes it; 404 if it is not the caller's
    GET    /            -> HTMLResponse(pages.landing_page())
    GET    /signup      -> HTMLResponse(pages.signup_page())
    GET    /login       -> HTMLResponse(pages.login_page())
    GET    /dashboard   -> HTMLResponse(pages.dashboard_page())

Requirements:
- Use pydantic BaseModel for request bodies so bad input returns 422, never 500.
  The signup/login model requires email (string) and password (string, min length 8).
  The trail model requires name (non-empty string), distance_km (float greater than 0)
  and date (string).
- Authentication reads an "Authorization: Bearer <token>" header and resolves it with
  storage.user_id_for_token. Any trails route without a valid token must return 401.
- Use storage for all persistence; do not write SQL in this module.
- Do not call uvicorn or define a main() - only the app and its routes.

Output only the Python module."""

API_TEST = """
import pathlib
p = pathlib.Path(__file__).parent / "trailmark.db"
if p.exists(): p.unlink()
import storage; storage.init_db()
from fastapi.testclient import TestClient
import api
c = TestClient(api.app)

assert c.get("/api/health").json() == {"status": "ok"}
r = c.post("/api/signup", json={"email": "a@b.io", "password": "longenough1"})
assert r.status_code == 201, (r.status_code, r.text)
tok = r.json()["token"]
assert c.post("/api/signup", json={"email": "a@b.io", "password": "longenough1"}).status_code == 409
assert c.post("/api/login", json={"email": "a@b.io", "password": "wrongpassword"}).status_code == 401
tok = c.post("/api/login", json={"email": "a@b.io", "password": "longenough1"}).json()["token"]

h = {"Authorization": f"Bearer {tok}"}
assert c.get("/api/trails").status_code == 401, "anonymous must be 401"
assert c.get("/api/trails", headers={"Authorization": "Bearer nope"}).status_code == 401
assert c.get("/api/trails", headers=h).json() == []
r = c.post("/api/trails", json={"name": "Ridge", "distance_km": 12.5, "date": "2026-05-02"}, headers=h)
assert r.status_code == 201, (r.status_code, r.text)
rows = c.get("/api/trails", headers=h).json()
assert len(rows) == 1
assert c.post("/api/signup", json={"email": "z@b.io", "password": "longenough1"}).status_code == 201
tok2 = c.post("/api/login", json={"email": "z@b.io", "password": "longenough1"}).json()["token"]
h2 = {"Authorization": f"Bearer {tok2}"}
assert c.get("/api/trails", headers=h2).json() == [], "cross-user leak"
assert c.delete(f"/api/trails/{rows[0]['id']}", headers=h2).status_code == 404
assert c.delete(f"/api/trails/{rows[0]['id']}", headers=h).status_code in (200, 204)

assert c.post("/api/signup", json={"email": "q@b.io"}).status_code == 422
assert c.post("/api/trails", json={"distance_km": 1}, headers=h).status_code == 422
assert c.post("/api/trails", json={"name": "x", "distance_km": "abc", "date": "2026-01-01"}, headers=h).status_code == 422
for path in ("/", "/signup", "/login", "/dashboard"):
    assert c.get(path).status_code == 200, path
print("OK")
"""

PIECES = [
    ("passwords", PW_SPEC, PW_TEST, HERE / "passwords.py"),
    ("storage", DB_SPEC, DB_TEST, HERE / "storage.py"),
    ("pages", HTML_SPEC, HTML_TEST, HERE / "pages.py"),
    ("api", API_SPEC, API_TEST, HERE / "api.py"),
]

if __name__ == "__main__":
    for name, spec, test, out in PIECES:
        build_piece(name, spec, test, out)
    LOG["total_seconds"] = round(time.time() - STARTED, 1)
    save_log()
    ok = sum(1 for p in LOG["pieces"] if p["passed"])
    print(f"\n{ok}/{len(PIECES)} pieces passed locally, "
          f"{len(LOG['escalations'])} escalation(s), "
          f"{LOG['tokens_out']} tokens out, {LOG['total_seconds']}s")
