-- Migration 038 -- Durable AI thread presence, work groups, and turn-time accounting.
--
-- A coordination session is a short-lived connection/heartbeat. These rows are the
-- durable identity of a ChatGPT/AI conversation and the logical request/project group
-- it contributes to. Turn rows make cumulative "worked for" time auditable instead
-- of deriving it from session age.

CREATE TABLE ai_work_groups (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    external_group_key TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'idle', 'error', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_ai_work_groups_project
    ON ai_work_groups(project_id, updated_at DESC);

CREATE UNIQUE INDEX idx_ai_work_groups_external
    ON ai_work_groups(project_id, external_group_key)
    WHERE external_group_key != '';

CREATE TABLE ai_threads (
    id TEXT PRIMARY KEY,
    work_group_id TEXT NOT NULL REFERENCES ai_work_groups(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL,
    runtime_id TEXT NOT NULL DEFAULT 'chatgpt',
    source TEXT NOT NULL DEFAULT 'connector'
        CHECK (source IN ('connector', 'browser_observer', 'managed_browser', 'cli', 'other')),
    external_thread_key TEXT NOT NULL,
    conversation_url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idle'
        CHECK (status IN ('active', 'idle', 'error', 'gone', 'archived')),
    current_task TEXT NOT NULL DEFAULT '',
    total_work_seconds REAL NOT NULL DEFAULT 0 CHECK (total_work_seconds >= 0),
    turn_count INTEGER NOT NULL DEFAULT 0 CHECK (turn_count >= 0),
    current_turn_started_at TEXT,
    last_activity_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(runtime_id, external_thread_key)
);

CREATE INDEX idx_ai_threads_group_time
    ON ai_threads(work_group_id, total_work_seconds DESC, updated_at DESC);

CREATE INDEX idx_ai_threads_project_status
    ON ai_threads(project_id, status, last_seen_at DESC);

CREATE TABLE ai_thread_turns (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES ai_threads(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_seconds REAL CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    duration_source TEXT NOT NULL DEFAULT 'wall_clock'
        CHECK (duration_source IN ('ui_display', 'wall_clock', 'reported', 'recovered')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'success', 'error', 'cancelled')),
    prompt_label TEXT NOT NULL DEFAULT '',
    summary_md TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_ai_thread_turns_thread
    ON ai_thread_turns(thread_id, started_at DESC);


-- Local browser companion observations exist before a ChatGPT tab has identified
-- which Synapse project/request it belongs to. They let the operator count real
-- generating tabs immediately; bootstrap later attaches the same external key
-- to a durable ai_threads row without duplicating it.
CREATE TABLE chatgpt_tab_observations (
    external_thread_key TEXT PRIMARY KEY,
    runtime_id TEXT NOT NULL DEFAULT 'chatgpt',
    browser_tab_id TEXT NOT NULL DEFAULT '',
    conversation_url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idle'
        CHECK (status IN ('active', 'idle', 'error', 'gone')),
    current_task TEXT NOT NULL DEFAULT '',
    generation_started_at TEXT,
    last_duration_seconds REAL
        CHECK (last_duration_seconds IS NULL OR last_duration_seconds >= 0),
    last_error TEXT NOT NULL DEFAULT '',
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_chatgpt_tab_observations_status
    ON chatgpt_tab_observations(status, last_seen_at DESC);
