-- Migration 013 -- local LLM assistant (ADR-0014).
-- A single settings row (the assistant is OFF by default), persisted chats,
-- and their messages. The engine itself is Ollama; this only stores the
-- conversation + the user's opt-in. Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS assistant_settings (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    enabled       INTEGER NOT NULL DEFAULT 0,
    default_model TEXT,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assistant_chats (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT 'New chat',
    model      TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS assistant_chats_recent_idx
    ON assistant_chats (updated_at DESC);

CREATE TABLE IF NOT EXISTS assistant_messages (
    id         TEXT PRIMARY KEY,
    chat_id    TEXT NOT NULL REFERENCES assistant_chats(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS assistant_messages_chat_idx
    ON assistant_messages (chat_id, created_at);
