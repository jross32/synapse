"""Trailmark - a small trail-logging app. Single-file FastAPI + SQLite, no build step.

Kept to one file on purpose: the whole thing is about 400 lines, and splitting it across a
package would add navigation cost without buying separation that anything actually needs.

Security choices worth stating, since they are the ones that would matter if this grew:

* Passwords are hashed with PBKDF2-HMAC-SHA256, 200k iterations, per-user random salt.
  Stored as ``algorithm$iterations$salt$hash`` so the parameters travel with the value and
  can be raised later without stranding existing rows.
* Session tokens are 32 random bytes from ``secrets``, stored hashed. A leaked database
  therefore does not hand over live sessions.
* Every trail query is scoped by ``user_id`` in the SQL itself rather than filtered after
  the fact, so there is no path where forgetting a check leaks another user's rows.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

DB_PATH = Path(__file__).parent / "trailmark.db"
PBKDF2_ROUNDS = 200_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ----------------------------------------------------------------------- storage


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with closing(connect()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at    REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trails (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                distance_km REAL NOT NULL,
                date        TEXT NOT NULL,
                created_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS trails_by_user ON trails(user_id);
            """
        )


# ----------------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, want = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        got = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                  bytes.fromhex(salt_hex), int(rounds))
    except (ValueError, AttributeError):
        return False
    # Constant-time: a timing difference here leaks how much of the hash matched.
    return hmac.compare_digest(got.hex(), want)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ----------------------------------------------------------------------- schemas


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("that does not look like an email address")
        return v


class TrailIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    distance_km: float = Field(gt=0, le=10_000)
    date: str = Field(min_length=4, max_length=32)

    @field_validator("date")
    @classmethod
    def iso_date(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v.strip()):
            raise ValueError("date must be YYYY-MM-DD")
        return v.strip()


# ----------------------------------------------------------------------- app


app = FastAPI(title="Trailmark", docs_url=None, redoc_url=None)


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
    """Never leak a stack trace, and never answer a bad request with a 500."""
    return JSONResponse(status_code=500, content={"error": "internal error"})


def current_user(request: Request) -> sqlite3.Row:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="sign in to continue")
    token = header.split(" ", 1)[1].strip()
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ?", (hash_token(token),)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="that session is no longer valid")
    return row


def issue_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with closing(connect()) as conn, conn:
        conn.execute("INSERT INTO sessions(token_hash, user_id, created_at) VALUES (?,?,?)",
                     (hash_token(token), user_id, time.time()))
    return token


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/signup", status_code=201)
async def signup(body: Credentials) -> dict[str, Any]:
    with closing(connect()) as conn, conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (body.email,)).fetchone():
            raise HTTPException(status_code=409, detail="that email is already registered")
        cur = conn.execute(
            "INSERT INTO users(email, password_hash, created_at) VALUES (?,?,?)",
            (body.email, hash_password(body.password), time.time()))
        user_id = int(cur.lastrowid)
    return {"token": issue_session(user_id), "email": body.email}


@app.post("/api/login")
async def login(body: Credentials) -> dict[str, Any]:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (body.email,)).fetchone()
    # Same message and same work either way, so the response cannot be used to discover
    # which emails are registered.
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="email or password is incorrect")
    return {"token": issue_session(int(row["id"])), "email": row["email"]}


@app.post("/api/logout")
async def logout(request: Request) -> dict[str, bool]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1].strip()
        with closing(connect()) as conn, conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
    return {"ok": True}


@app.get("/api/trails")
async def list_trails(user: sqlite3.Row = Depends(current_user)) -> list[dict[str, Any]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT id, name, distance_km, date FROM trails WHERE user_id = ? "
            "ORDER BY date DESC, id DESC", (user["id"],)).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/trails", status_code=201)
async def create_trail(body: TrailIn,
                       user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    with closing(connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO trails(user_id, name, distance_km, date, created_at) "
            "VALUES (?,?,?,?,?)",
            (user["id"], body.name.strip(), body.distance_km, body.date, time.time()))
        return {"id": int(cur.lastrowid), "name": body.name.strip(),
                "distance_km": body.distance_km, "date": body.date}


@app.delete("/api/trails/{trail_id}")
async def delete_trail(trail_id: int,
                       user: sqlite3.Row = Depends(current_user)) -> dict[str, bool]:
    with closing(connect()) as conn, conn:
        cur = conn.execute("DELETE FROM trails WHERE id = ? AND user_id = ?",
                           (trail_id, user["id"]))
    # Scoped by user_id in the statement, so another user's row simply does not match and
    # the answer is indistinguishable from "no such trail" - which is what it should be.
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="no such trail")
    return {"ok": True}


# ----------------------------------------------------------------------- frontend

BASE_CSS = """
:root{--bg:#0f1210;--card:#171b18;--line:#2a302c;--ink:#e8eae8;--dim:#9aa39c;
      --accent:#6fcf87;--danger:#e0736b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:560px;margin:0 auto;padding:24px 18px 64px}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;
       padding:16px 18px;border-bottom:1px solid var(--line)}
.brand{font-weight:700;letter-spacing:-.02em;font-size:19px}
.brand span{color:var(--accent)}
h1{font-size:27px;line-height:1.2;letter-spacing:-.02em;margin:28px 0 10px}
p.lede{color:var(--dim);margin:0 0 26px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px}
label{display:block;font-size:14px;color:var(--dim);margin:14px 0 6px}
input{width:100%;padding:13px 12px;border-radius:10px;border:1px solid var(--line);
      background:#10130f;color:var(--ink);font-size:16px}
input:focus{outline:2px solid var(--accent);outline-offset:1px}
button{width:100%;margin-top:18px;padding:14px;border-radius:10px;border:0;
       background:var(--accent);color:#08120c;font-weight:650;font-size:16px;
       min-height:44px;cursor:pointer}
button.secondary{background:transparent;color:var(--ink);border:1px solid var(--line)}
button.link{width:auto;margin:0;padding:10px 14px;background:transparent;color:var(--ink);
            border:1px solid var(--line);min-height:44px}
.row{display:flex;gap:10px;flex-wrap:wrap}
.row button{width:auto;flex:1 1 140px}
.msg{margin-top:14px;padding:11px 12px;border-radius:9px;font-size:14px;display:none}
.msg.err{display:block;background:rgba(224,115,107,.12);border:1px solid rgba(224,115,107,.4);
         color:#ffb3ad}
.msg.ok{display:block;background:rgba(111,207,135,.12);border:1px solid rgba(111,207,135,.4);
        color:var(--accent)}
.trail{display:flex;justify-content:space-between;align-items:center;gap:12px;
       padding:14px 0;border-bottom:1px solid var(--line)}
.trail:last-child{border-bottom:0}
.trail h3{margin:0;font-size:16px;font-weight:600}
.trail small{color:var(--dim)}
.del{width:auto;margin:0;min-height:44px;min-width:44px;background:transparent;
     border:1px solid var(--line);color:var(--danger);border-radius:9px;padding:8px 12px}
.empty{color:var(--dim);text-align:center;padding:30px 10px}
a{color:var(--accent)}
@media(min-width:700px){h1{font-size:34px}}
"""

NAV = """<header><div class="brand">Trail<span>mark</span></div>
<div id="nav"></div></header>"""

SHELL = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - Trailmark</title><style>{css}</style></head>
<body>{nav}<main class="wrap">{body}</main><script>{js}</script></body></html>"""

COMMON_JS = """
const tok = () => localStorage.getItem('tm_token');
const setTok = t => localStorage.setItem('tm_token', t);
const clearTok = () => localStorage.removeItem('tm_token');
function say(el, text, kind){ el.textContent = text; el.className = 'msg ' + kind; }
async function api(path, opts){
  const o = opts || {}; o.headers = Object.assign({'Content-Type':'application/json'}, o.headers||{});
  if (tok()) o.headers['Authorization'] = 'Bearer ' + tok();
  const r = await fetch(path, o);
  let data = null; try { data = await r.json(); } catch(e) {}
  if (!r.ok) throw new Error((data && (data.detail || data.error)) || ('Request failed (' + r.status + ')'));
  return data;
}
(function nav(){
  const n = document.getElementById('nav'); if(!n) return;
  n.innerHTML = tok()
    ? '<button class="link" onclick="logout()">Log out</button>'
    : '<a href="/login"><button class="link">Log in</button></a>';
})();
async function logout(){ try { await api('/api/logout', {method:'POST'}); } catch(e){} clearTok(); location.href='/'; }
"""


def page(title: str, body: str, js: str = "") -> HTMLResponse:
    return HTMLResponse(SHELL.format(title=title, css=BASE_CSS, nav=NAV, body=body,
                                     js=COMMON_JS + js))


@app.get("/", response_class=HTMLResponse)
async def landing() -> HTMLResponse:
    return page("Log every trail", """
      <h1>Every trail you walk, in one place.</h1>
      <p class="lede">Trailmark keeps a simple record of where you have been - name,
      distance and date. No accounts to manage, no clutter.</p>
      <div class="card">
        <div class="row">
          <a href="/signup" style="flex:1 1 140px"><button>Sign up</button></a>
          <a href="/login" style="flex:1 1 140px"><button class="secondary">Log in</button></a>
        </div>
      </div>""")


@app.get("/signup", response_class=HTMLResponse)
async def signup_page() -> HTMLResponse:
    return page("Sign up", """
      <h1>Create your account</h1>
      <p class="lede">Eight characters or more for the password.</p>
      <div class="card"><form id="f" novalidate>
        <label for="email">Email</label>
        <input id="email" name="email" type="email" autocomplete="email" required>
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="new-password" required>
        <button type="submit">Create account</button>
        <div id="msg" class="msg"></div>
      </form>
      <p style="margin:16px 0 0;color:var(--dim);font-size:14px">
        Already have one? <a href="/login">Log in</a></p></div>""", """
      document.getElementById('f').addEventListener('submit', async e => {
        e.preventDefault();
        const m = document.getElementById('msg');
        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;
        if (!email || !password) { say(m, 'Enter an email and a password.', 'err'); return; }
        if (password.length < 8) { say(m, 'Password must be at least 8 characters.', 'err'); return; }
        try {
          const d = await api('/api/signup', {method:'POST', body: JSON.stringify({email, password})});
          setTok(d.token); location.href = '/dashboard';
        } catch (err) { say(m, err.message, 'err'); }
      });""")


@app.get("/login", response_class=HTMLResponse)
async def login_page() -> HTMLResponse:
    return page("Log in", """
      <h1>Welcome back</h1>
      <p class="lede">Log in to see your trails.</p>
      <div class="card"><form id="f" novalidate>
        <label for="email">Email</label>
        <input id="email" name="email" type="email" autocomplete="email" required>
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required>
        <button type="submit">Log in</button>
        <div id="msg" class="msg"></div>
      </form>
      <p style="margin:16px 0 0;color:var(--dim);font-size:14px">
        New here? <a href="/signup">Create an account</a></p></div>""", """
      document.getElementById('f').addEventListener('submit', async e => {
        e.preventDefault();
        const m = document.getElementById('msg');
        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;
        if (!email || !password) { say(m, 'Enter an email and a password.', 'err'); return; }
        try {
          const d = await api('/api/login', {method:'POST', body: JSON.stringify({email, password})});
          setTok(d.token); location.href = '/dashboard';
        } catch (err) { say(m, err.message, 'err'); }
      });""")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page() -> HTMLResponse:
    return page("Your trails", """
      <h1>Your trails</h1>
      <p class="lede">Add a walk and it stays on this device's account.</p>
      <div class="card"><form id="f" novalidate>
        <label for="name">Trail name</label>
        <input id="name" required>
        <label for="distance">Distance (km)</label>
        <input id="distance" type="number" step="0.1" min="0.1" required>
        <label for="date">Date</label>
        <input id="date" type="date" required>
        <button type="submit">Add trail</button>
        <div id="msg" class="msg"></div>
      </form></div>
      <div class="card" style="margin-top:16px"><div id="list">
        <div class="empty">Loading...</div></div></div>""", """
      if (!tok()) location.href = '/login';
      const list = document.getElementById('list');
      function render(rows){
        if (!rows.length) { list.innerHTML =
          '<div class="empty">No trails yet. Add your first one above.</div>'; return; }
        list.innerHTML = rows.map(t =>
          '<div class="trail"><div><h3>' + esc(t.name) + '</h3>' +
          '<small>' + t.distance_km + ' km &middot; ' + esc(t.date) + '</small></div>' +
          '<button class="del" data-id="' + t.id + '" aria-label="Delete ' + esc(t.name) + '">Delete</button></div>'
        ).join('');
        list.querySelectorAll('.del').forEach(b => b.onclick = async () => {
          try { await api('/api/trails/' + b.dataset.id, {method:'DELETE'}); load(); }
          catch (err) { say(document.getElementById('msg'), err.message, 'err'); }
        });
      }
      function esc(s){ return String(s).replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
      async function load(){
        try { render(await api('/api/trails')); }
        catch (err) { if (String(err.message).match(/sign in|no longer valid/i)) { clearTok(); location.href='/login'; }
                      else list.innerHTML = '<div class="empty">' + esc(err.message) + '</div>'; }
      }
      document.getElementById('f').addEventListener('submit', async e => {
        e.preventDefault();
        const m = document.getElementById('msg');
        const name = document.getElementById('name').value.trim();
        const distance_km = parseFloat(document.getElementById('distance').value);
        const date = document.getElementById('date').value;
        if (!name) { say(m, 'Give the trail a name.', 'err'); return; }
        if (!(distance_km > 0)) { say(m, 'Distance must be a number greater than zero.', 'err'); return; }
        if (!date) { say(m, 'Pick a date.', 'err'); return; }
        try {
          await api('/api/trails', {method:'POST', body: JSON.stringify({name, distance_km, date})});
          say(m, 'Added.', 'ok'); e.target.reset(); load();
        } catch (err) { say(m, err.message, 'err'); }
      });
      load();""")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Trailmark.")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    init_db()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
