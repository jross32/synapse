from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from synapse_accounts.app import SocialIdentity, create_app, consume_reserved_token, issue_reserved_token
from synapse_accounts.config import AccountsSettings
from synapse_accounts.db import Account, OAuthState, PasswordResetToken, session_scope


def _settings(tmp_path: Path) -> AccountsSettings:
    return AccountsSettings(
        database_url=f"sqlite:///{(tmp_path / 'accounts.sqlite').as_posix()}",
        public_base_url="http://127.0.0.1:8788",
        access_token_ttl_seconds=900,
        refresh_token_ttl_seconds=3600,
        oauth_state_ttl_seconds=900,
        oauth_handoff_ttl_seconds=300,
        request_timeout_seconds=8,
        google_client_id="demo-google-client",
        google_client_secret="demo-google-secret",
        github_client_id=None,
        github_client_secret=None,
    )


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(_settings(tmp_path)))


def test_native_signup_and_signin_work_with_username_or_email(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        signup = client.post(
            "/v1/auth/signup",
            json={
                "username": "justin",
                "email": "justin@example.com",
                "password": "hunter4242",
                "display_name": "Justin Ross",
            },
        )
        signin_email = client.post(
            "/v1/auth/signin",
            json={"login": "justin@example.com", "password": "hunter4242"},
        )
        signin_username = client.post(
            "/v1/auth/signin",
            json={"login": "justin", "password": "hunter4242"},
        )
    assert signup.status_code == 200, signup.text
    assert signup.json()["account"]["username"] == "justin"
    assert signup.json()["account"]["account_provider"] == "native"
    assert signin_email.status_code == 200, signin_email.text
    assert signin_username.status_code == 200, signin_username.text


def test_duplicate_username_and_email_are_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        first = client.post(
            "/v1/auth/signup",
            json={
                "username": "justin",
                "email": "justin@example.com",
                "password": "hunter4242",
                "display_name": "Justin Ross",
            },
        )
        dup_email = client.post(
            "/v1/auth/signup",
            json={
                "username": "other",
                "email": "justin@example.com",
                "password": "hunter4242",
                "display_name": "Other",
            },
        )
        dup_username = client.post(
            "/v1/auth/signup",
            json={
                "username": "justin",
                "email": "other@example.com",
                "password": "hunter4242",
                "display_name": "Other",
            },
        )
    assert first.status_code == 200, first.text
    assert dup_email.status_code == 409
    assert dup_username.status_code == 409


def test_refresh_rotates_session_and_signout_revokes_it(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        signup = client.post(
            "/v1/auth/signup",
            json={
                "username": "justin",
                "email": "justin@example.com",
                "password": "hunter4242",
                "display_name": "Justin Ross",
            },
        )
        refresh_1 = client.post(
            "/v1/auth/refresh",
            json={"refresh_token": signup.json()["refresh_token"]},
        )
        refresh_old = client.post(
            "/v1/auth/refresh",
            json={"refresh_token": signup.json()["refresh_token"]},
        )
        signout = client.post(
            "/v1/auth/signout",
            json={"refresh_token": refresh_1.json()["refresh_token"]},
            headers={"Authorization": f"Bearer {refresh_1.json()['access_token']}"},
        )
        refresh_revoked = client.post(
            "/v1/auth/refresh",
            json={"refresh_token": refresh_1.json()["refresh_token"]},
        )
    assert refresh_1.status_code == 200, refresh_1.text
    assert refresh_old.status_code == 401
    assert signout.status_code == 204
    assert refresh_revoked.status_code == 401


def test_sync_document_round_trips_per_account(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        signup = client.post(
            "/v1/auth/signup",
            json={
                "username": "justin",
                "email": "justin@example.com",
                "password": "hunter4242",
                "display_name": "Justin Ross",
            },
        )
        token = signup.json()["access_token"]
        put_doc = client.put(
            "/v1/sync/document",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "document": {
                    "preferences": {"theme": "hacker"},
                    "catalog_preferences": [{"item_key": "tool:cloudtap"}],
                }
            },
        )
        get_doc = client.get(
            "/v1/sync/document",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert put_doc.status_code == 200, put_doc.text
    assert get_doc.status_code == 200, get_doc.text
    assert get_doc.json()["document"]["preferences"]["theme"] == "hacker"


def test_social_signin_rejects_unsafe_implicit_linking(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    service = app.state.accounts_service
    with session_scope(service.session_factory) as db:
        db.add(
            Account(
                id="account-native",
                username="justin",
                username_normalized="justin",
                email="justin@example.com",
                email_normalized="justin@example.com",
                password_hash="hashed",
                display_name="Justin",
            )
        )
    with session_scope(service.session_factory) as db:
        state = OAuthState(
            state="state-1",
            provider="google",
            mode="signin",
            callback_url="http://127.0.0.1:7878/api/v1/profile/auth/callback",
            link_account_id=None,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        with pytest.raises(HTTPException) as exc:
            service._resolve_social_account(
                db,
                provider="google",
                state_row=state,
                social=SocialIdentity(
                    provider="google",
                    subject="google-user-1",
                    email="justin@example.com",
                    display_name="Justin Ross",
                    avatar_url=None,
                    email_verified=True,
                ),
            )
    assert exc.value.status_code == 409


def test_reserved_password_reset_tokens_can_be_issued_and_consumed(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    service = app.state.accounts_service
    with session_scope(service.session_factory) as db:
        db.add(
            Account(
                id="account-native",
                username="justin",
                username_normalized="justin",
                email="justin@example.com",
                email_normalized="justin@example.com",
                password_hash="hashed",
                display_name="Justin",
            )
        )
    with session_scope(service.session_factory) as db:
        token = issue_reserved_token(
            db,
            PasswordResetToken,
            account_id="account-native",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    with session_scope(service.session_factory) as db:
        consumed_account = consume_reserved_token(db, PasswordResetToken, token=token)
    assert consumed_account == "account-native"
