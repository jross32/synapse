-- Durable ChatGPT UI worker-chat registry.
--
-- A worker chat is intentionally separate from a coordination session:
-- coordination sessions are short-lived presence records for one active run,
-- while a ChatGPT conversation may be resumed for the same or a related work
-- item days later. Synapse keeps the URL and relationship history; ChatGPT
-- remains the source of the conversation itself.

CREATE TABLE IF NOT EXISTS chatgpt_worker_chats (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    owner_session_id TEXT,
    last_session_id TEXT,
    role_id TEXT,
    chatgpt_project_name TEXT NOT NULL DEFAULT 'Synapse2GPT Workers',
    conversation_url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'starting'
        CHECK (status IN ('starting', 'active', 'idle', 'failed', 'archived')),
    archived_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    archived_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (owner_session_id) REFERENCES agent_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (last_session_id) REFERENCES agent_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (role_id) REFERENCES agent_role_templates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chatgpt_worker_chat_work_items (
    worker_chat_id TEXT NOT NULL,
    work_item_id TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT 'primary'
        CHECK (relation IN ('primary', 'continued', 'related')),
    is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
    linked_at TEXT NOT NULL,
    PRIMARY KEY (worker_chat_id, work_item_id),
    FOREIGN KEY (worker_chat_id) REFERENCES chatgpt_worker_chats(id) ON DELETE CASCADE,
    FOREIGN KEY (work_item_id) REFERENCES agent_work_items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chatgpt_worker_chats_project_status
    ON chatgpt_worker_chats(project_id, status, last_used_at DESC);

CREATE INDEX IF NOT EXISTS idx_chatgpt_worker_chats_owner
    ON chatgpt_worker_chats(owner_session_id, last_used_at DESC);

CREATE INDEX IF NOT EXISTS idx_chatgpt_worker_chat_links_worker
    ON chatgpt_worker_chat_work_items(worker_chat_id, linked_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chatgpt_worker_chat_current_work_item
    ON chatgpt_worker_chat_work_items(work_item_id)
    WHERE is_current = 1;
