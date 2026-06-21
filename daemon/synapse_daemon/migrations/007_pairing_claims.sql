-- Migration 007 -- durable paired-device sessions + reconnect claims
-- v0.1.36 follow-up. Keep paired_devices as the durable trust record, but
-- move active bearer sessions and short-lived reconnect handoff claims into
-- their own tables. Never edit a shipped migration.

CREATE TABLE paired_device_tokens (
    id            TEXT PRIMARY KEY,
    device_id     TEXT NOT NULL REFERENCES paired_devices(id) ON DELETE CASCADE,
    token_sha256  TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL,
    last_seen_at  TEXT,
    revoked       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS paired_device_tokens_sha_idx
    ON paired_device_tokens (token_sha256) WHERE revoked = 0;

CREATE INDEX IF NOT EXISTS paired_device_tokens_device_idx
    ON paired_device_tokens (device_id) WHERE revoked = 0;

INSERT INTO paired_device_tokens (id, device_id, token_sha256, created_at, last_seen_at, revoked)
SELECT
    'legacy-' || id,
    id,
    token_sha256,
    created_at,
    last_seen_at,
    revoked
FROM paired_devices;

CREATE TABLE pairing_claims (
    id           TEXT PRIMARY KEY,
    device_id    TEXT NOT NULL REFERENCES paired_devices(id) ON DELETE CASCADE,
    claim_sha256 TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    used_at      TEXT,
    revoked      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS pairing_claims_sha_idx
    ON pairing_claims (claim_sha256) WHERE revoked = 0 AND used_at IS NULL;
