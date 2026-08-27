-- Migration 035 -- Project-scoped AI collaboration rooms (ADR-0037).
--
-- Durable rooms sit on top of ADR-0024's agent_sessions presence registry.
-- They do not spawn workers or replace squads; they give already-connected AIs
-- a shared, inspectable channel for explicit messages, status, decisions and handoffs.
-- Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS collaboration_rooms (
    id                    TEXT PRIMARY KEY,
    project_id            TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name                  TEXT NOT NULL,
    goal_md               TEXT NOT NULL DEFAULT '',
    summary_md            TEXT NOT NULL DEFAULT '',
    status                TEXT NOT NULL DEFAULT 'open'
                              CHECK (status IN ('open', 'archived')),
    created_by_session_id TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    metadata_json         TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS collaboration_rooms_project_idx
    ON collaboration_rooms (project_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS collaboration_room_members (
    room_id       TEXT NOT NULL REFERENCES collaboration_rooms(id) ON DELETE CASCADE,
    session_id    TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    role_label    TEXT NOT NULL DEFAULT '',
    joined_at     TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    left_at       TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (room_id, session_id)
);

CREATE INDEX IF NOT EXISTS collaboration_room_members_room_idx
    ON collaboration_room_members (room_id, left_at, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS collaboration_room_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id       TEXT NOT NULL REFERENCES collaboration_rooms(id) ON DELETE CASCADE,
    session_id    TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL,
    kind          TEXT NOT NULL DEFAULT 'message'
                      CHECK (kind IN ('message', 'status', 'handoff', 'decision', 'question', 'answer')),
    body_md       TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS collaboration_room_messages_room_idx
    ON collaboration_room_messages (room_id, id);
