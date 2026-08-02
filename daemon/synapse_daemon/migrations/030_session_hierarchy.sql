-- 030: session hierarchy + resumable identity (PLAN 7 Phase 1, ADR-0035)
--
-- The Live rail became unusable as an operator surface: 84 sessions, 72 of them
-- top-level, for what the operator experienced as a handful of tasks. Two causes,
-- both fixed here:
--
--   1. A returning main AI could not re-attach. `register_session` always assigned
--      `seq = MAX(seq)+1`, and `SESSION_STALE_SECONDS = 90` marks a session `gone`
--      between wakes, so one autonomous agent minted a new number every wake
--      (#079..#083 were all the same Claude). `resume_key` gives a session a stable
--      identity so the same AI re-attaches instead of multiplying.
--
--   2. Every daemon-spawned squad worker was registered as a *top-level* session and
--      burned a `seq`, even though the UI already showed workers nested inside the
--      squad drawer. `parent_session_id` makes that nesting explicit in the data, so
--      the rail can show roots only without losing a worker's own record.
--
-- `seq` becomes optional: only root sessions are numbered. SQLite treats NULLs as
-- distinct in a UNIQUE index, so the existing `agent_sessions_seq_idx` tolerates any
-- number of unnumbered children without change.

ALTER TABLE agent_sessions ADD COLUMN parent_session_id TEXT
    REFERENCES agent_sessions(id) ON DELETE SET NULL;

-- Stable identity for "the same AI, reconnecting". Deliberately NOT unique on its
-- own: a key may legitimately recur across ended sessions. Uniqueness is scoped to
-- live sessions by the partial index below, so history is preserved.
ALTER TABLE agent_sessions ADD COLUMN resume_key TEXT;

CREATE INDEX IF NOT EXISTS agent_sessions_parent_idx
    ON agent_sessions (parent_session_id)
    WHERE parent_session_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS agent_sessions_resume_key_live_idx
    ON agent_sessions (resume_key)
    WHERE resume_key IS NOT NULL AND ended_at IS NULL;

-- Backfill: existing daemon-spawned workers are identifiable by `coder_thread_id`
-- (set to the worker's PTY session id at launch). Their parent is the session that
-- created the squad, which `activity_journal` already records -- so the link is
-- recoverable from data we already have rather than lost.
UPDATE agent_sessions
   SET parent_session_id = (
        SELECT j.session_id
          FROM activity_journal j
          JOIN agent_work_items w ON w.squad_id = j.squad_id
         WHERE w.pty_session_id = agent_sessions.coder_thread_id
           AND j.session_id IS NOT NULL
           AND j.session_id <> agent_sessions.id
         ORDER BY j.created_at ASC
         LIMIT 1
   )
 WHERE coder_thread_id IS NOT NULL
   AND parent_session_id IS NULL;
