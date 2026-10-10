-- 047: lightweight persistent staff conversation history.
CREATE TABLE IF NOT EXISTS staff_chat_messages (
    id TEXT PRIMARY KEY,
    staff_member_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staff_chat_messages_staff_idx
    ON staff_chat_messages(staff_member_id, created_at, id);
