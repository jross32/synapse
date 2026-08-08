-- 031: persistent conversations with local models
--
-- The local-AI layer added in 0.1.113 could run a one-shot agent task, but a user
-- coding with a local model needs what they already expect from every coding chat:
-- a conversation that survives a reload, a list of past chats to return to, and a
-- sensible title without having to name anything.
--
-- Two tables rather than a JSON blob per chat, for three reasons:
--   * messages are appended far more often than chats are created, and appending a
--     row is cheaper and safer than rewriting a growing document;
--   * a partial reply from an interrupted stream can be stored and repaired in place;
--   * tool calls belong to the message that made them, so the transcript can be
--     replayed exactly as it happened rather than reconstructed.
--
-- `title` is filled from the opening prompt on first save. It is a plain column and
-- not derived on read, so a user can rename a chat later and have it stick.
--
-- `project_id` is nullable on purpose: a local chat is often a scratch conversation
-- with no project attached, and forcing one would push people into inventing
-- throwaway projects.

CREATE TABLE IF NOT EXISTS local_chats (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    model         TEXT NOT NULL,
    mode          TEXT NOT NULL DEFAULT 'auto',
    workspace     TEXT,
    project_id    TEXT REFERENCES projects(id) ON DELETE SET NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived_at   TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- The sidebar lists most-recently-touched first, and that is the only ordering the
-- UI ever asks for.
CREATE INDEX IF NOT EXISTS local_chats_updated_idx
    ON local_chats (updated_at DESC);

CREATE TABLE IF NOT EXISTS local_chat_messages (
    id              TEXT PRIMARY KEY,
    chat_id         TEXT NOT NULL REFERENCES local_chats(id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    tool_calls_json TEXT,
    tokens_out      INTEGER,
    duration_s      REAL,
    created_at      TEXT NOT NULL
);

-- Every read is "give me this chat's messages in order", so index the pair rather
-- than chat_id alone.
CREATE UNIQUE INDEX IF NOT EXISTS local_chat_messages_seq_idx
    ON local_chat_messages (chat_id, seq);
