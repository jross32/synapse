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

class RecordRequest(BaseModel):
    title: str
    amount: float
    date: str

def get_current_user(request: Request):
    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    user_id = storage.user_id_for_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user_id

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.post("/api/signup", status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest):
    if storage.get_user_by_email(request.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    password_hash = hash_password(request.password)
    user_id = storage.create_user(request.email, password_hash)
    token = storage.create_session(user_id)
    return {"token": token}

@app.post("/api/login", status_code=status.HTTP_201_CREATED)
async def login(request: LoginRequest):
    user = storage.get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = storage.create_session(user["id"])
    return {"token": token}

@app.post("/api/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request):
    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    storage.delete_session(token)
    return {"ok": True}

@app.get("/api/records", dependencies=[Depends(get_current_user)])
async def get_records(user_id: int = Depends(get_current_user)):
    records = storage.list_records(user_id)
    return records

@app.post("/api/records", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_current_user)])
async def create_record(request: RecordRequest, user_id: int = Depends(get_current_user)):
    record_id = storage.add_record(user_id, request.title, request.amount, request.date)
    return {"id": record_id}

@app.delete("/api/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(get_current_user)])
async def delete_record(record_id: int, user_id: int = Depends(get_current_user)):
    if not storage.get_record_by_id(record_id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    storage.delete_record(record_id, user_id)

@app.get("/", response_class=HTMLResponse)
async def landing_page():
    return pages.landing_page()

@app.get("/signup", response_class=HTMLResponse)
async def signup_page():
    return pages.signup_page()

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return pages.login_page()

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return pages.dashboard_page()