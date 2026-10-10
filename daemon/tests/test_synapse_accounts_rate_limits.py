from fastapi.testclient import TestClient
from synapse_accounts.rate_limits import AuthRateLimiter
from synapse_accounts.app import create_app
from synapse_accounts.config import AccountsSettings


def test_throttle_rejects_after_limit_and_is_client_scoped():
    limiter = AuthRateLimiter()
    assert limiter.allow("client-one", "/v1/auth/signin", limit=2, window_seconds=60)
    assert limiter.allow("client-one", "/v1/auth/signin", limit=2, window_seconds=60)
    assert not limiter.allow("client-one", "/v1/auth/signin", limit=2, window_seconds=60)
    assert limiter.allow("client-two", "/v1/auth/signin", limit=2, window_seconds=60)


def test_public_signup_rate_limit_fails_closed(tmp_path):
    cfg = AccountsSettings(
        database_url="sqlite:///" + str(tmp_path / "rate-limit.sqlite").replace("\\", "/"),
        public_base_url="https://accounts.example.test", access_token_ttl_seconds=900,
        refresh_token_ttl_seconds=3600, oauth_state_ttl_seconds=900,
        oauth_handoff_ttl_seconds=300, request_timeout_seconds=8,
        google_client_id=None, google_client_secret=None,
        github_client_id=None, github_client_secret=None,
    )
    with TestClient(create_app(cfg)) as client:
        for _ in range(5):
            result = client.post("/v1/auth/signup", json={})
            assert result.status_code == 422
        blocked = client.post("/v1/auth/signup", json={})
        assert blocked.status_code == 429
