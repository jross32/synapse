-- Migration 012 -- per-project decision records, backlog, and version history
-- ADR-0011. Each managed project carries its own ADRs (with a quick-idea ->
-- promote-to-numbered lifecycle), a durable backlog, and a version changelog.
-- Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS project_adrs (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    number        INTEGER,
    title         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'idea'
                  CHECK (status IN ('idea', 'draft', 'proposed', 'accepted', 'rejected', 'superseded')),
    body_md       TEXT NOT NULL DEFAULT '',
    tags_json     TEXT NOT NULL DEFAULT '[]',
    supersedes_id TEXT REFERENCES project_adrs(id) ON DELETE SET NULL,
    source        TEXT NOT NULL DEFAULT 'desktop',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    decided_at    TEXT
);

CREATE INDEX IF NOT EXISTS project_adrs_project_idx
    ON project_adrs (project_id, status);

CREATE TABLE IF NOT EXISTS project_backlog (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    body_md      TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'todo'
                 CHECK (status IN ('todo', 'in_progress', 'done', 'wontfix')),
    priority     TEXT NOT NULL DEFAULT 'medium'
                 CHECK (priority IN ('low', 'medium', 'high')),
    order_index  INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'desktop',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS project_backlog_project_idx
    ON project_backlog (project_id, status, order_index);

CREATE TABLE IF NOT EXISTS project_versions (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version     TEXT NOT NULL,
    released_at TEXT,
    changes_md  TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'desktop',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS project_versions_project_idx
    ON project_versions (project_id, created_at DESC);
