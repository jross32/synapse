from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
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

@app.on_event("startup")
async def startup():
    await storage.init_db()

def get_user_from_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    token = auth_header.split()[1]
    user_id = storage.user_id_for_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user_id

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.post("/api/signup", status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest):
    if storage.get_user_by_email(request.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    password_hash = hash_password(request.password)
    user_id = await storage.create_user(request.email, password_hash)
    token = await storage.create_session(user_id)
    return {"token": token}

@app.post("/api/login")
async def login(request: LoginRequest):
    user = storage.get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    token = await storage.create_session(user["id"])
    return {"token": token}

@app.post("/api/logout")
async def logout(token: str = Depends(get_user_from_token)):
    await storage.delete_session(token)
    return {"ok": True}

@app.get("/api/records", response_model=list[dict])
async def get_records(token: str = Depends(get_user_from_token)):
    user_id = storage.user_id_for_token(token)
    return await storage.list_records(user_id)

@app.post("/api/records", status_code=status.HTTP_201_CREATED)
async def create_record(request: dict, token: str = Depends(get_user_from_token)):
    user_id = storage.user_id_for_token(token)
    await storage.add_record(user_id, request["title"], request["amount"], request["date"])
    return {"ok": True}

@app.delete("/api/records/{id}")
async def delete_record(id: int, token: str = Depends(get_user_from_token)):
    user_id = storage.user_id_for_token(token)
    await storage.delete_record(user_id, id)
    return {"ok": True}

@app.get("/")
async def root(request: Request):
    return HTMLResponse(pages.index_page())

@app.get("/signup")
async def signup_page(request: Request):
    return HTMLResponse(pages.signup_page())

@app.get("/login")
async def login_page(request: Request):
    return HTMLResponse(pages.login_page())

@app.get("/dashboard")
async def dashboard_page(request: Request, token: str = Depends(get_user_from_token)):
    return HTMLResponse(pages.dashboard_page())