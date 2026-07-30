-- 028: persisted AI-activity notifications (ADR-0028, PLAN 5 Phase 2).
--
-- The operator-facing notification feed: one row per milestone an AI hits while
-- driving Synapse (session connected, squad created, work launched/handed off,
-- idea filed to the inbox, project launched/errored, tool ran). Written by the
-- event->notification projector in activity.py; read by the Notification Center.

CREATE TABLE IF NOT EXISTS activity_notifications (
    id               TEXT PRIMARY KEY,
    session_id       TEXT,             -- coordination agent_sessions.id when known
    seq              INTEGER,          -- the session's #001-style number when known
    kind             TEXT NOT NULL,    -- e.g. 'session.connected', 'squad.created'
    level            TEXT NOT NULL DEFAULT 'info',  -- green | yellow | red | info
    title            TEXT NOT NULL,
    body_md          TEXT NOT NULL DEFAULT '',
    links_json       TEXT NOT NULL DEFAULT '[]',    -- [{label, intent}] NavigationIntent shapes
    token_usage_json TEXT,                          -- squad/session token rollup when known
    created_at       TEXT NOT NULL,
    read_at          TEXT
);

CREATE INDEX IF NOT EXISTS activity_notifications_unread_idx
    ON activity_notifications (read_at, created_at DESC);
