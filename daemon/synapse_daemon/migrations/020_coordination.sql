-- Migration 020 -- Native multi-AI coordination (ADR-0024).
--
-- Presence registry + advisory file-lane claims so concurrent AI coders
-- (Claude Code, Codex, squad workers, humans) share one live picture of who
-- is working what, on which files -- and overlapping edits are DETECTED
-- instead of hand-noticed.
--
-- Lanes are ADVISORY: external CLI processes edit disk directly and the daemon
-- cannot hard-lock them. The one enforceable choke point is the pre-commit
-- overlap check (scripts/coordination-preflight.ps1). See ADR-0024 for the
-- enforce-vs-advise boundary. Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS agent_sessions (
    id                TEXT PRIMARY KEY,
    project_id        TEXT REFERENCES projects(id) ON DELETE CASCADE,
    runtime_id        TEXT NOT NULL DEFAULT '',
    agent_label       TEXT NOT NULL DEFAULT '',
    coder_thread_id   TEXT,
    task              TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'idle', 'blocked', 'holding', 'gone')),
    last_intent       TEXT NOT NULL DEFAULT '',
    registered_at     TEXT NOT NULL,
    last_heartbeat_at TEXT NOT NULL,
    ended_at          TEXT,
    metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS agent_sessions_project_idx
    ON agent_sessions (project_id, status, last_heartbeat_at DESC);

CREATE TABLE IF NOT EXISTS file_lanes (
    id              TEXT PRIMARY KEY,
    project_id      TEXT REFERENCES projects(id) ON DELETE CASCADE,
    session_id      TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL,
    owner_label     TEXT NOT NULL DEFAULT '',
    runtime_id      TEXT NOT NULL DEFAULT '',
    path_globs_json TEXT NOT NULL DEFAULT '[]',
    task_ref        TEXT NOT NULL DEFAULT '',
    note            TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'released', 'expired')),
    claimed_at      TEXT NOT NULL,
    heartbeat_at    TEXT NOT NULL,
    released_at     TEXT,
    metadata_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS file_lanes_project_active_idx
    ON file_lanes (project_id, status, claimed_at DESC);

CREATE INDEX IF NOT EXISTS file_lanes_session_idx
    ON file_lanes (session_id);
