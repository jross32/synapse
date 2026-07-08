-- 026: make coder_threads.project_id optional (Plan 2 Phase A -- project-free "New chat").
--
-- runner:foreign_keys=off
-- ^ REQUIRED. This is a table rebuild with child FKs; without foreign_keys OFF the DROP TABLE below
--   fires ON DELETE CASCADE on coder_messages/coder_runs/coder_review_passes/coder_runtime_switches
--   and destroys all coder history. The runner toggles the pragma + runs foreign_key_check for us.
--
-- coder_threads was the only coder_* table with a NOT NULL project_id + ON DELETE CASCADE; its
-- siblings (coder_runs, coder_messages, coder_review_passes in migration 018) already use the
-- nullable ON DELETE SET NULL shape. This rebuilds coder_threads to match, so a thread can live in
-- a "General" (project-less) scope and survive its project being deleted.
--
-- SQLite can't ALTER a column's NOT NULL / FK constraint, so this is the standard table-rebuild.
-- Verified safe inside the runner's BEGIN IMMEDIATE transaction (foreign_keys=ON): data is
-- preserved, child FKs (coder_messages/coder_runs -> coder_threads.id) stay intact per
-- PRAGMA foreign_key_check, and ON DELETE SET NULL nulls a thread's project_id when its project is
-- removed.

CREATE TABLE coder_threads_new (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    active_runtime_id TEXT,
    active_provider TEXT,
    active_model TEXT,
    workspace_context_mode TEXT NOT NULL DEFAULT 'project',
    pinned INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    thread_kind TEXT NOT NULL DEFAULT 'chat',
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_message_at TEXT,
    last_run_at TEXT
);

INSERT INTO coder_threads_new SELECT * FROM coder_threads;

DROP TABLE coder_threads;

ALTER TABLE coder_threads_new RENAME TO coder_threads;

-- Recreate the exact index from migration 018 (dropped with the old table). It backs the
-- list_threads ORDER BY (archived ASC, pinned DESC, updated_at DESC) per project.
CREATE INDEX IF NOT EXISTS coder_threads_project_recent_idx
    ON coder_threads (project_id, archived, pinned DESC, updated_at DESC);
