-- 042: Durable Synapse Active Tasks.
--
-- Synapse-owned recurring work is intentionally separate from ChatGPT's built-in
-- task/automation product. Tasks are project-scoped, durable across daemon
-- restarts, non-overlapping by default, and dispatch into an external worker
-- runtime (initially Foreman) through a narrow scheduler boundary.

CREATE TABLE IF NOT EXISTS active_tasks (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    prompt              TEXT NOT NULL DEFAULT '',
    dispatch_kind       TEXT NOT NULL DEFAULT 'foreman_iteration',
    preferred_runtime   TEXT NOT NULL DEFAULT 'chatgpt_web',
    schedule_kind       TEXT NOT NULL DEFAULT 'interval',
    interval_seconds    INTEGER,
    next_run_at         TEXT,
    end_at              TEXT,
    max_runs            INTEGER,
    run_count           INTEGER NOT NULL DEFAULT 0,
    enabled             INTEGER NOT NULL DEFAULT 1,
    no_overlap          INTEGER NOT NULL DEFAULT 1,
    max_runtime_seconds INTEGER NOT NULL DEFAULT 3600,
    last_started_at     TEXT,
    last_finished_at    TEXT,
    last_status         TEXT,
    last_error          TEXT NOT NULL DEFAULT '',
    last_dispatch_ref   TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    source              TEXT NOT NULL DEFAULT 'desktop'
);

CREATE INDEX IF NOT EXISTS active_tasks_due_idx
    ON active_tasks (enabled, next_run_at);
CREATE INDEX IF NOT EXISTS active_tasks_project_idx
    ON active_tasks (project_id, enabled, next_run_at);

CREATE TABLE IF NOT EXISTS active_task_runs (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES active_tasks(id) ON DELETE CASCADE,
    scheduled_for   TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'queued',
    manual          INTEGER NOT NULL DEFAULT 0,
    dispatch_ref    TEXT,
    error           TEXT NOT NULL DEFAULT '',
    detail_json     TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS active_task_runs_task_time_idx
    ON active_task_runs (task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS active_task_runs_status_idx
    ON active_task_runs (status, created_at DESC);
