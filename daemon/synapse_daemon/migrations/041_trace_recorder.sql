-- 041: Synapse Trace / Flight Recorder.
--
-- Stores normalized, privacy-filtered receipts for AI/tool actions and runtime
-- observations. Raw hidden reasoning is never stored; only explicit summaries,
-- safe metadata, outcomes, timings, and redacted details.

CREATE TABLE IF NOT EXISTS trace_events (
    id              TEXT PRIMARY KEY,
    occurred_at     TEXT NOT NULL,
    source          TEXT NOT NULL,
    category        TEXT NOT NULL,
    action          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'info',
    severity        TEXT NOT NULL DEFAULT 'info',
    summary         TEXT NOT NULL DEFAULT '',
    project_id      TEXT,
    session_id      TEXT,
    correlation_id  TEXT,
    duration_ms     REAL,
    error_code      TEXT,
    dedupe_key      TEXT UNIQUE,
    details_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS trace_events_time_idx
    ON trace_events (occurred_at DESC);

CREATE INDEX IF NOT EXISTS trace_events_category_time_idx
    ON trace_events (category, occurred_at DESC);

CREATE INDEX IF NOT EXISTS trace_events_project_time_idx
    ON trace_events (project_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS trace_events_session_time_idx
    ON trace_events (session_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS trace_events_status_time_idx
    ON trace_events (status, occurred_at DESC);
