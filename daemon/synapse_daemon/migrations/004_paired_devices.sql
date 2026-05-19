-- Migration 004 -- paired devices (Milestone H · v0.1.11)
-- Device pairing for the mobile Web UI. A paired device is remembered by the
-- SHA-256 of its bearer token (the raw token is shown to the device once and
-- never stored). Pairing codes themselves are short-lived and kept in daemon
-- memory only -- they never touch the DB. Never edit a shipped migration.

CREATE TABLE paired_devices (
    id            TEXT PRIMARY KEY,           -- uuid4
    name          TEXT NOT NULL,              -- user-facing label
    token_sha256  TEXT NOT NULL UNIQUE,       -- sha256 hex of the device token
    created_at    TEXT NOT NULL,              -- ISO 8601 UTC
    last_seen_at  TEXT,                       -- ISO 8601 UTC; NULL until first use
    revoked       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS paired_devices_token_idx
    ON paired_devices (token_sha256) WHERE revoked = 0;
