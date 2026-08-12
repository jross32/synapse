from fastapi import FastAPI, Request, Depends, HTTPException, status
from pydantic import BaseModel
from passwords import hash_password, verify_password
import storage
import pages

app = FastAPI()

class SignupRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.post("/api/signup")
async def signup(request: Request, data: SignupRequest):
    if storage.get_user_by_email(data.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    password_hash = hash_password(data.password)
    user_id = storage.create_user(data.email, password_hash)
    token = storage.create_session(user_id)
    return {"token": token}

@app.post("/api/login")
async def login(request: Request, data: LoginRequest):
    user = storage.get_user_by_email(data.email)
    if not user or not verify_password(data.password, user['password_hash']):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    token = storage.create_session(user['id'])
    return {"token": token}

@app.post("/api/logout")
async def logout(request: Request):
    token = request.headers.get("Authorization").split()[1]
    storage.delete_session(token)
    return {"ok": True}

@app.get("/api/trails")
async def get_trails(request: Request):
    user_id = await auth_helper(request)
    trails = storage.list_records(user_id)
    return trails

@app.post("/api/trails")
async def create_trail(request: Request, data: TrailRequest):
    user_id = await auth_helper(request)
    trail_id = storage.add_record(user_id, data.name, data.distance_km, data.date)
    return {"id": trail_id}, status.HTTP_201_CREATED

@app.delete("/api/trails/{id}")
async def delete_trail(request: Request, id: int):
    user_id = await auth_helper(request)
    if not storage.delete_record(id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {"ok": True}

@app.get("/")
async def landing_page():
    return HTMLResponse(pages.landing_page())

@app.get("/signup")
async def signup_page():
    return HTMLResponse(pages.signup_page())

@app.get("/login")
async def login_page():
    return HTMLResponse(pages.login_page())

@app.get("/dashboard")
async def dashboard_page(request: Request):
    user_id = await auth_helper(request)
    trails = storage.list_records(user_id)
    return HTMLResponse(pages.dashboard_page(trails=trails))

async def auth_helper(request: Request) -> int:
    token = request.headers.get("Authorization").split()[1]
    user_id = storage.user_id_for_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user_id