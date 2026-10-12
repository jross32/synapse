from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from synapse_daemon import railway_oauth as oauth
from synapse_daemon.routes_watchdogs import build_watchdogs_router

class Profile:
    def __init__(self, email="justinwross32@gmail.com", verified=True, uid="owner"):
        self.email, self.verified, self.uid = email, verified, uid
    def summary(self, *, refresh_remote=False):
        return SimpleNamespace(signed_in=True, email_verified=self.verified, user_id=self.uid, email=self.email)

def test_owner_only():
    assert oauth.owner(Profile()) == "owner"
    assert oauth.owner(Profile(email="another@example.com")) is None
    assert oauth.owner(Profile(verified=False)) is None
    with patch.dict("os.environ", {"SYNAPSE_DEVELOPER_USER_ID": "different"}):
        assert oauth.owner(Profile()) is None

def test_authorization_pkce(monkeypatch):
    monkeypatch.setenv("SYNAPSE_RAILWAY_OAUTH_CLIENT_ID", "example-client-id")
    a = oauth.make_authorization("owner", "http://127.0.0.1:7878/api/v1/system/railway-oauth/callback")
    q = parse_qs(urlparse(a["url"]).query)
    assert q["code_challenge_method"] == ["S256"]
    assert q["scope"][0].split() == oauth.SCOPES.split()
    assert q["state"] == [a["state"]]
    assert "client_secret" not in a["url"]
    with pytest.raises(ValueError):
        oauth.make_authorization("owner", "http://localhost:7878/callback")

def test_other_account_cannot_use_oauth(tmp_path):
    app = FastAPI()
    app.include_router(build_watchdogs_router(tmp_path, Profile(email="another@example.com")), prefix="/api/v1")
    c = TestClient(app)
    for url in ("/api/v1/system/railway-oauth/status", "/api/v1/system/railway-oauth/start"):
        r = c.post(url) if url.endswith("start") else c.get(url)
        assert r.status_code == 403
    assert c.delete("/api/v1/system/railway-oauth").status_code == 403

def test_owner_unconfigured(monkeypatch, tmp_path):
    monkeypatch.delenv("SYNAPSE_RAILWAY_OAUTH_CLIENT_ID", raising=False)
    app = FastAPI()
    app.include_router(build_watchdogs_router(tmp_path, Profile()), prefix="/api/v1")
    c = TestClient(app)
    assert c.get("/api/v1/system/railway-oauth/status").json()["configured"] is False
    assert c.post("/api/v1/system/railway-oauth/start").status_code == 409
