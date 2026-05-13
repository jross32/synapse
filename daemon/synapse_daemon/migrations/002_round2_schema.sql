-- Migration 002 — Round 2 contract schema
-- Synapse v0.1.2 — operationalises contracts #17–#28.
-- Never edit this file after it has shipped; always add a new migration.

-- Contract #17 — Health-check + #18 Restart policy + #19 Resource caps:
-- columns on the projects table.
ALTER TABLE projects ADD COLUMN health_probe_json        TEXT;
ALTER TABLE projects ADD COLUMN restart_policy_json      TEXT;
ALTER TABLE projects ADD COLUMN max_rss_mb               INTEGER;
ALTER TABLE projects ADD COLUMN max_cpu_percent          INTEGER;
ALTER TABLE projects ADD COLUMN current_health           TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE projects ADD COLUMN last_health_at           TEXT;

-- Contract #20 — Project dependencies (many-to-many).
CREATE TABLE IF NOT EXISTS project_dependencies (
    project_id      TEXT    NOT NULL,
    requires_id     TEXT    NOT NULL,
    PRIMARY KEY (project_id, requires_id),
    FOREIGN KEY (project_id)  REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (requires_id) REFERENCES projects(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS project_dependencies_requires_idx
    ON project_dependencies (requires_id);

-- Contract #21 — Universal search index.
-- Each row is one searchable token for one entity. UI queries via
-- `GET /api/v1/search?q=...`.
CREATE TABLE IF NOT EXISTS search_index (
    entity_type     TEXT    NOT NULL,         -- 'project' | 'tool' | 'action' | 'setting'
    entity_id       TEXT    NOT NULL,
    token           TEXT    NOT NULL,         -- lower-cased
    weight          REAL    NOT NULL DEFAULT 1.0,
    PRIMARY KEY (entity_type, entity_id, token)
);
CREATE INDEX IF NOT EXISTS search_index_token_idx
    ON search_index (token);

-- Contract #22 — Native system notifications opt-out per event-kind.
CREATE TABLE IF NOT EXISTS notification_preferences (
    event_kind      TEXT    PRIMARY KEY,      -- 'process.crashed', 'tunnel.live', etc.
    enabled         INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT    NOT NULL
);

-- Contract #25 — Secrets stored encrypted at rest (DPAPI on Windows).
-- ciphertext is opaque to SQLite; only the daemon's user can decrypt.
CREATE TABLE IF NOT EXISTS project_secrets (
    project_id      TEXT    NOT NULL,
    key             TEXT    NOT NULL,
    ciphertext      BLOB    NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    PRIMARY KEY (project_id, key),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
