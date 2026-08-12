"""HTTP layer for the Trailmark blueprint build.

ESCALATED PIECE - written by Claude after the local model exhausted its repairs.

The failure is the same one it hit in the previous run, and it is a genuine capability limit
rather than a careless slip: it writes ``Depends(storage.user_id_for_token)``, handing a plain
storage function to FastAPI as a dependency. FastAPI inspects that function's signature, sees
a parameter named ``token``, and treats it as a *query* parameter - so an anonymous request is
answered with ``422 Field required: query.token`` instead of ``401``. The error message
("anonymous must be 401") describes the symptom without hinting at the cause, and no number of
repairs bridged it.

Everything this imports - passwords, storage, pages - was written by a local model and passed
its own contract and acceptance checks unaided.
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


class RecordIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    amount: float = Field(gt=0, le=1_000_000)
    date: str = Field(min_length=4, max_length=32)


def current_user_id(request: Request) -> int:
    """Resolve the bearer token to a user id, or refuse.

    A FastAPI dependency must be a callable the framework *invokes with the request* - which
    is exactly the distinction the local model could not recover from its error message.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="sign in to continue")
    user_id = storage.user_id_for_token(header.split(" ", 1)[1].strip())
    if user_id is None:
        raise HTTPException(status_code=401, detail="that session is no longer valid")
    return int(user_id)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/signup", status_code=201)
async def signup(body: Credentials) -> dict[str, str]:
    try:
        user_id = storage.create_user(body.email.strip().lower(),
                                      hash_password(body.password))
    except ValueError:
        raise HTTPException(status_code=409, detail="that email is already registered")
    return {"token": storage.create_session(int(user_id))}


@app.post("/api/login")
async def login(body: Credentials) -> dict[str, str]:
    user = storage.get_user_by_email(body.email.strip().lower())
    # One message for both failures, so the response cannot be used to enumerate accounts.
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="email or password is incorrect")
    return {"token": storage.create_session(int(user["id"]))}


@app.post("/api/logout")
async def logout(request: Request) -> dict[str, bool]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        storage.delete_session(header.split(" ", 1)[1].strip())
    return {"ok": True}


@app.get("/api/records")
async def list_records(user_id: int = Depends(current_user_id)) -> list[dict]:
    return storage.list_records(user_id)


@app.post("/api/records", status_code=201)
async def create_record(body: RecordIn,
                        user_id: int = Depends(current_user_id)) -> dict:
    return storage.add_record(user_id, body.title.strip(), body.amount, body.date)


@app.delete("/api/records/{record_id}")
async def delete_record(record_id: int,
                        user_id: int = Depends(current_user_id)) -> dict[str, bool]:
    if not storage.delete_record(record_id, user_id):
        raise HTTPException(status_code=404, detail="no such record")
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
