-- Migration 001 — initial schema
-- Synapse v0.1.1 — establishes the core tables required by the design contracts.
-- Never edit this file after it has shipped; always add a new migration.

-- Migration bookkeeping (Contract #9).
CREATE TABLE IF NOT EXISTS schema_migrations (
    number      INTEGER PRIMARY KEY,
    slug        TEXT    NOT NULL,
    applied_at  TEXT    NOT NULL   -- ISO 8601 UTC
);

-- Audit log (Contract #11) — every state-changing action lands here.
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc   TEXT    NOT NULL,
    entity_type     TEXT    NOT NULL,         -- 'project', 'tool', 'process', etc.
    entity_id       TEXT,
    action          TEXT    NOT NULL,         -- 'launch', 'stop', 'rename', 'delete', etc.
    source          TEXT    NOT NULL,         -- 'desktop' | 'mobile' | 'tray' | 'cli' | 'auto'
    result          TEXT    NOT NULL,         -- 'success' | 'error'
    error_code      TEXT,
    details_json    TEXT
);
CREATE INDEX IF NOT EXISTS audit_log_entity_idx
    ON audit_log (entity_type, entity_id, timestamp_utc DESC);

-- Projects (managed apps) — Contract #1 editable everywhere.
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT    PRIMARY KEY,      -- kebab-case (Contract #10)
    name            TEXT    NOT NULL,
    path            TEXT    NOT NULL,         -- working dir
    launch_cmd      TEXT    NOT NULL,         -- e.g. 'npm start'
    env_json        TEXT,                     -- JSON object of env vars
    icon            TEXT,
    thumbnail       TEXT,
    description     TEXT,
    category        TEXT,
    health_url      TEXT,                     -- optional probe (Round 2 will formalise)
    expected_port   INTEGER,
    status          TEXT    NOT NULL DEFAULT 'idle',
    last_error_code TEXT,
    last_error_msg  TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    last_transition_at TEXT NOT NULL,
    deleted_at      TEXT                       -- soft delete
);

-- Tools (built-in / dropped-in Synapse cards) — registered from manifests.
CREATE TABLE IF NOT EXISTS tools (
    id              TEXT    PRIMARY KEY,
    name            TEXT    NOT NULL,
    category        TEXT,
    icon            TEXT,
    description     TEXT,
    manifest_json   TEXT    NOT NULL,         -- full manifest snapshot
    installed_at    TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    disabled        INTEGER NOT NULL DEFAULT 0
);

-- Managed processes (Contract #6 orphan reconciliation).
CREATE TABLE IF NOT EXISTS managed_processes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT    NOT NULL,         -- 'project' | 'tool'
    entity_id       TEXT    NOT NULL,
    pid             INTEGER NOT NULL,
    cmdline         TEXT    NOT NULL,         -- joined argv at spawn time
    started_at      TEXT    NOT NULL,
    stopped_at      TEXT,
    stop_reason     TEXT,                     -- 'user' | 'crashed' | 'daemon-restart' | 'pid-recycled'
    log_path        TEXT    NOT NULL,         -- Contract #3
    status          TEXT    NOT NULL DEFAULT 'launching'
);
CREATE INDEX IF NOT EXISTS managed_processes_active_idx
    ON managed_processes (status)
    WHERE stopped_at IS NULL;

-- User preferences for the "Don't ask again" confirm dialogs (Contract #12).
CREATE TABLE IF NOT EXISTS confirm_preferences (
    action_key      TEXT    PRIMARY KEY,      -- e.g. 'project.delete', 'process.kill'
    suppress        INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT    NOT NULL
);

-- Settings KV — daemon port, theme, update channel, etc. (Contract #1).
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT    PRIMARY KEY,
    value_json      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
