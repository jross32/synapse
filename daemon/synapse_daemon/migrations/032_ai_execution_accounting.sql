-- 032: one durable execution and accounting contract for every AI runtime

CREATE TABLE IF NOT EXISTS ai_runtime_capacity (
    runtime_id       TEXT PRIMARY KEY,
    state            TEXT NOT NULL DEFAULT 'unknown',
    reason_code      TEXT,
    detail           TEXT,
    evidence_source  TEXT NOT NULL DEFAULT 'none',
    evidence_at      TEXT,
    retry_after      TEXT,
    reset_at         TEXT,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_executions (
    id                TEXT PRIMARY KEY,
    kind              TEXT NOT NULL,
    project_id        TEXT REFERENCES projects(id) ON DELETE SET NULL,
    runtime_id        TEXT NOT NULL,
    model             TEXT,
    effort            TEXT,
    authority         TEXT,
    source_type       TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    pty_session_id    TEXT,
    state             TEXT NOT NULL DEFAULT 'reserved',
    process_outcome   TEXT,
    work_outcome      TEXT,
    accounting_state  TEXT NOT NULL DEFAULT 'pending',
    exit_code         INTEGER,
    started_at        TEXT,
    ended_at          TEXT,
    metadata_json     TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE(pty_session_id)
);

CREATE INDEX IF NOT EXISTS ai_executions_runtime_idx
    ON ai_executions (runtime_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_executions_project_idx
    ON ai_executions (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_executions_source_idx
    ON ai_executions (source_type, source_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_usage_observations (
    id                 TEXT PRIMARY KEY,
    execution_id       TEXT NOT NULL REFERENCES ai_executions(id) ON DELETE CASCADE,
    provenance         TEXT NOT NULL,
    source             TEXT NOT NULL,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    cached_tokens      INTEGER,
    total_tokens       INTEGER,
    cost_usd           REAL,
    credits            REAL,
    requests           INTEGER,
    parser_version     TEXT,
    evidence_hash      TEXT,
    captured_at        TEXT NOT NULL,
    metadata_json      TEXT NOT NULL DEFAULT '{}',
    UNIQUE(execution_id, source)
);

CREATE INDEX IF NOT EXISTS ai_usage_execution_idx
    ON ai_usage_observations (execution_id, captured_at);
