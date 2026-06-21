-- Migration 008 -- agent squads + work items (Sessions-centric AI squads)
-- v0.1.36-dev follow-up. Adds durable role templates, squad state, and
-- structured work items that map onto the existing PTY session runtime.
-- Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS agent_role_templates (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    description           TEXT NOT NULL DEFAULT '',
    preferred_runtimes_json TEXT NOT NULL DEFAULT '[]',
    default_visibility    TEXT NOT NULL CHECK (default_visibility IN ('lead', 'helper')),
    context_mode          TEXT NOT NULL CHECK (context_mode IN ('full', 'standard', 'minimal')),
    can_delegate          INTEGER NOT NULL DEFAULT 1,
    prompt_preamble_md    TEXT NOT NULL DEFAULT '',
    enabled               INTEGER NOT NULL DEFAULT 1,
    sort_order            INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_squads (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    goal_md           TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL CHECK (status IN ('active', 'paused', 'completed')),
    lead_role_id      TEXT REFERENCES agent_role_templates(id) ON DELETE SET NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    last_activity_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS agent_squads_project_idx
    ON agent_squads (project_id, status);

CREATE INDEX IF NOT EXISTS agent_squads_activity_idx
    ON agent_squads (last_activity_at DESC);

CREATE TABLE IF NOT EXISTS agent_work_items (
    id                  TEXT PRIMARY KEY,
    squad_id            TEXT NOT NULL REFERENCES agent_squads(id) ON DELETE CASCADE,
    parent_id           TEXT REFERENCES agent_work_items(id) ON DELETE CASCADE,
    title               TEXT NOT NULL,
    instructions_md     TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL CHECK (status IN ('queued', 'running', 'handoff', 'blocked', 'completed')),
    assigned_role_id    TEXT REFERENCES agent_role_templates(id) ON DELETE SET NULL,
    preferred_runtime   TEXT,
    pty_session_id      TEXT,
    summary_md          TEXT,
    blockers_md         TEXT,
    files_touched_json  TEXT NOT NULL DEFAULT '[]',
    suggested_next_role TEXT,
    transcript_file_id  TEXT REFERENCES project_files(id) ON DELETE SET NULL,
    opened_in_tab       INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    completed_at        TEXT
);

CREATE INDEX IF NOT EXISTS agent_work_items_squad_idx
    ON agent_work_items (squad_id, created_at);

CREATE INDEX IF NOT EXISTS agent_work_items_parent_idx
    ON agent_work_items (parent_id);

CREATE INDEX IF NOT EXISTS agent_work_items_session_idx
    ON agent_work_items (pty_session_id) WHERE pty_session_id IS NOT NULL;
