"""HTTP layer for Trailmark.

ESCALATED PIECE - written by Claude, not by a local model, after five local attempts.

The local model's failure here was conceptual rather than careless, and worth recording.
It wrote ``Depends(storage.user_id_for_token)``, passing a plain storage function straight
to FastAPI as a dependency. FastAPI then introspects that function's signature, sees a
parameter named ``token``, and concludes it is a *query parameter* - so an anonymous
request produced ``422 Field required: query.token`` instead of ``401``. Four repair rounds
with the error "anonymous must be 401" never bridged the gap, because the message says what
is wrong without hinting at why, and the fix requires knowing that a dependency is a
callable FastAPI *calls*, not a value it looks up.

Everything this module imports - passwords, storage, pages - was written by the local
model and passed its own tests unaided.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import pages
import storage
from passwords import hash_password, verify_password

app = FastAPI(title="Trailmark", docs_url=None, redoc_url=None)


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)


class TrailIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    distance_km: float = Field(gt=0, le=10_000)
    date: str = Field(min_length=4, max_length=32)


def current_user_id(request: Request) -> int:
    """Resolve the bearer token to a user id, or refuse.

    A dependency has to be a callable FastAPI invokes with the request - which is exactly
    the distinction the local model missed.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="sign in to continue")
    user_id = storage.user_id_for_token(header.split(" ", 1)[1].strip())
    if user_id is None:
        raise HTTPException(status_code=401, detail="that session is no longer valid")
    return user_id


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/signup", status_code=201)
async def signup(body: Credentials) -> dict[str, str]:
    try:
        user_id = storage.create_user(body.email.strip().lower(), hash_password(body.password))
    except ValueError:
        raise HTTPException(status_code=409, detail="that email is already registered")
    return {"token": storage.create_session(user_id)}


@app.post("/api/login")
async def login(body: Credentials) -> dict[str, str]:
    user = storage.get_user_by_email(body.email.strip().lower())
    # One message for both cases, so the response cannot be used to enumerate accounts.
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="email or password is incorrect")
    return {"token": storage.create_session(int(user["id"]))}


@app.post("/api/logout")
async def logout(request: Request) -> dict[str, bool]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        storage.delete_session(header.split(" ", 1)[1].strip())
    return {"ok": True}


@app.get("/api/trails")
async def list_trails(user_id: int = Depends(current_user_id)) -> list[dict]:
    return storage.list_trails(user_id)


@app.post("/api/trails", status_code=201)
async def create_trail(body: TrailIn, user_id: int = Depends(current_user_id)) -> dict:
    return storage.add_trail(user_id, body.name.strip(), body.distance_km, body.date)


@app.delete("/api/trails/{trail_id}")
async def delete_trail(trail_id: int, user_id: int = Depends(current_user_id)) -> dict[str, bool]:
    if not storage.delete_trail(trail_id, user_id):
        raise HTTPException(status_code=404, detail="no such trail")
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def landing() -> HTMLResponse:
    return HTMLResponse(pages.landing_page())


@app.get("/signup", response_class=HTMLResponse)
async def signup_page() -> HTMLResponse:
    return HTMLResponse(pages.signup_page())


@app.get("/login", response_class=HTMLResponse)
async def login_page() -> HTMLResponse:
    return HTMLResponse(pages.login_page())


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page() -> HTMLResponse:
    return HTMLResponse(pages.dashboard_page())
