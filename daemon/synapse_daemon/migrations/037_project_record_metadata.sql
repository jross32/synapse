-- Migration 037 -- canonical AI chat/thread pointer per managed project
-- One last-write-wins URL lives alongside the durable project-record bundle so
-- every AI runtime can discover the same current thread instead of relying on
-- stale conversational memory. Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS project_record_metadata (
    project_id         TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    canonical_chat_url TEXT,
    updated_at         TEXT NOT NULL
);
