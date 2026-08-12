# Build spec — "Trailmark", a mobile-first full-stack app

Both arms build **exactly this**. The spec is written before either build starts and is not
changed afterwards, so neither arm gets a target the other did not have.

Stack is fixed so the comparison is about the *building*, not about library choices, and so
neither arm can win by picking something faster to install:

* **Backend** — Python + FastAPI + SQLite (all already present; zero installs)
* **Frontend** — plain HTML/CSS/JS served by the same app. No build step, no framework.
* **Port** — the app must accept `--port` and default to 8099.

## What it must do

A small trail-logging app. A visitor lands, signs up, logs in, and records hikes.

### Pages
1. **Landing** (`/`) — product name, one-line pitch, and links to Sign up and Log in.
   Must be readable and usable at 375px wide.
2. **Sign up** (`/signup`) — email + password. Rejects a duplicate email with a visible
   message rather than a blank failure.
3. **Log in** (`/login`) — email + password. Wrong credentials produce a visible error.
4. **Dashboard** (`/dashboard`) — requires login. Lists the signed-in user's trails, and
   has a form to add one (name, distance in km, date). Each trail can be deleted.
   Must show an empty state before any trail exists.

### API
| Method | Path | Behaviour |
|---|---|---|
| POST | `/api/signup` | `{email, password}` → creates user, returns a session token |
| POST | `/api/login` | `{email, password}` → returns a session token |
| POST | `/api/logout` | ends the session |
| GET | `/api/trails` | trails belonging to the caller only |
| POST | `/api/trails` | `{name, distance_km, date}` → creates one |
| DELETE | `/api/trails/{id}` | deletes one, only if it belongs to the caller |
| GET | `/api/health` | `{"status":"ok"}` |

### Rules that will be checked
* Passwords are **never** stored in plain text.
* `/api/trails` without a valid token returns **401**, not an empty list and not a 500.
* One user must not be able to read or delete another user's trails.
* Invalid input (missing fields, bad types) returns **4xx**, never a 500.
* The dashboard must not be reachable as a logged-out visitor.

## Deliverable
A single directory containing the app, runnable as:

    python app.py --port 8099

No other setup step. If it needs one, it has failed the spec.
