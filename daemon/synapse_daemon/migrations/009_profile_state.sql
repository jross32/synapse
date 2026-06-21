-- Migration 009 -- local-first profile/account/catalog state
-- Adds the daemon-owned profile/account/session cache, catalog preferences,
-- service connection records, and host inventory used by the optional
-- Synapse account/Profile hub.

CREATE TABLE profile_state (
    id                         INTEGER PRIMARY KEY CHECK (id = 1),
    supabase_url               TEXT,
    supabase_anon_key          TEXT,
    sync_enabled               INTEGER NOT NULL DEFAULT 0,
    user_id                    TEXT,
    email                      TEXT,
    display_name               TEXT,
    avatar_url                 TEXT,
    provider                   TEXT,
    provider_identities_json   TEXT NOT NULL DEFAULT '[]',
    access_token_cipher        BLOB,
    refresh_token_cipher       BLOB,
    access_token_expires_at    TEXT,
    current_host_id            TEXT,
    current_host_name          TEXT,
    current_host_platform      TEXT,
    last_sync_at               TEXT,
    last_sync_error            TEXT,
    created_at                 TEXT NOT NULL,
    updated_at                 TEXT NOT NULL
);

CREATE TABLE profile_oauth_states (
    state          TEXT PRIMARY KEY,
    provider       TEXT NOT NULL,
    code_verifier  TEXT NOT NULL,
    redirect_to    TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    expires_at     TEXT NOT NULL,
    used_at        TEXT
);

CREATE INDEX IF NOT EXISTS profile_oauth_states_exp_idx
    ON profile_oauth_states (expires_at);

CREATE TABLE catalog_preferences (
    item_key             TEXT PRIMARY KEY,
    kind                 TEXT NOT NULL,
    item_id              TEXT NOT NULL,
    favorite             INTEGER NOT NULL DEFAULT 0,
    last_used_at         TEXT,
    use_count            INTEGER NOT NULL DEFAULT 0,
    last_installed_at    TEXT,
    installed_host_ids_json TEXT NOT NULL DEFAULT '[]',
    updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS catalog_preferences_kind_item_idx
    ON catalog_preferences (kind, item_id);

CREATE TABLE service_connections (
    id                   TEXT PRIMARY KEY,
    provider             TEXT NOT NULL,
    display_name         TEXT NOT NULL,
    mode                 TEXT NOT NULL,
    portability          TEXT NOT NULL,
    status               TEXT NOT NULL,
    details_json         TEXT NOT NULL DEFAULT '{}',
    last_verified_at     TEXT,
    last_host_id         TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS service_connections_provider_idx
    ON service_connections (provider);

CREATE TABLE profile_hosts (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    platform             TEXT NOT NULL,
    current_host         INTEGER NOT NULL DEFAULT 0,
    last_seen_at         TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS profile_hosts_seen_idx
    ON profile_hosts (last_seen_at DESC);
