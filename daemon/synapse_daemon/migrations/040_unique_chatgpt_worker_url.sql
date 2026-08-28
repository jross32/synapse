-- Migration 040 -- one durable worker row per real ChatGPT conversation.
-- Empty URLs are allowed while a worker is starting; once ChatGPT assigns a
-- conversation URL, no second worker record may claim that same conversation.

CREATE UNIQUE INDEX IF NOT EXISTS idx_chatgpt_worker_chats_conversation_url
    ON chatgpt_worker_chats(conversation_url)
    WHERE conversation_url != '';
