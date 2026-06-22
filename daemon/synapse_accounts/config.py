from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AccountsSettings:
    database_url: str
    public_base_url: str
    access_token_ttl_seconds: int
    refresh_token_ttl_seconds: int
    oauth_state_ttl_seconds: int
    oauth_handoff_ttl_seconds: int
    request_timeout_seconds: int
    google_client_id: str | None
    google_client_secret: str | None
    github_client_id: str | None
    github_client_secret: str | None


def load_settings() -> AccountsSettings:
    default_db = Path("data") / "synapse-accounts.sqlite"
    return AccountsSettings(
        database_url=os.getenv(
            "SYNAPSE_ACCOUNTS_DATABASE_URL",
            f"sqlite:///{default_db.as_posix()}",
        ),
        public_base_url=os.getenv(
            "SYNAPSE_ACCOUNTS_BASE_URL",
            "http://127.0.0.1:8788",
        ).rstrip("/"),
        access_token_ttl_seconds=int(
            os.getenv("SYNAPSE_ACCOUNTS_ACCESS_TTL_SECONDS", "900")
        ),
        refresh_token_ttl_seconds=int(
            os.getenv("SYNAPSE_ACCOUNTS_REFRESH_TTL_SECONDS", str(60 * 60 * 24 * 30))
        ),
        oauth_state_ttl_seconds=int(
            os.getenv("SYNAPSE_ACCOUNTS_OAUTH_STATE_TTL_SECONDS", "900")
        ),
        oauth_handoff_ttl_seconds=int(
            os.getenv("SYNAPSE_ACCOUNTS_OAUTH_HANDOFF_TTL_SECONDS", "300")
        ),
        request_timeout_seconds=int(
            os.getenv("SYNAPSE_ACCOUNTS_REQUEST_TIMEOUT_SECONDS", "12")
        ),
        google_client_id=os.getenv("SYNAPSE_GOOGLE_CLIENT_ID"),
        google_client_secret=os.getenv("SYNAPSE_GOOGLE_CLIENT_SECRET"),
        github_client_id=os.getenv("SYNAPSE_GITHUB_CLIENT_ID"),
        github_client_secret=os.getenv("SYNAPSE_GITHUB_CLIENT_SECRET"),
    )

