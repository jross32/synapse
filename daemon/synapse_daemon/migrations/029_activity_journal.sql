-- 029: structured operator journal for Live View (ADR-0033).
--
-- Unlike terminal output, these rows are short, deliberate receipts: current
-- focus, plan/decision summaries, actions, evidence, blockers, squad state, and
-- MCP attachment/use.  session_id may be NULL only for daemon-projected squad
-- lifecycle events; AI-authored journal entries always belong to a registered
-- coordination session.

CREATE TABLE IF NOT EXISTS activity_journal (
    id               TEXT PRIMARY KEY,
    session_id       TEXT,
    category         TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'info',
    title            TEXT NOT NULL,
    summary_md       TEXT NOT NULL DEFAULT '',
    squad_id         TEXT,
    work_item_id     TEXT,
    mcp_server_id    TEXT,
    tool_name        TEXT,
    authority        TEXT NOT NULL DEFAULT 'none',
    source           TEXT NOT NULL DEFAULT 'agent',
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS activity_journal_session_idx
    ON activity_journal (session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS activity_journal_squad_idx
    ON activity_journal (squad_id, created_at DESC);
