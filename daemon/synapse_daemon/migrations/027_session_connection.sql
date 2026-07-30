-- 027: AI-session connection identity (ADR-0028, PLAN 5 Phase 1).
--
-- Adds the operator-facing connection fields to agent_sessions:
--   seq              -- the human-friendly monotonic session number (#001, #002, ...)
--   connection_level -- green | yellow | red (see connection_codes.py)
--   connection_code  -- stable machine code, e.g. 'ok', 'degraded.mcp_unavailable'
--
-- Backfill: existing sessions get seq by registration order (id as tiebreaker)
-- so history stays stable. New sessions compute seq = MAX(seq)+1 at register time.

ALTER TABLE agent_sessions ADD COLUMN seq INTEGER;
ALTER TABLE agent_sessions ADD COLUMN connection_level TEXT NOT NULL DEFAULT 'green';
ALTER TABLE agent_sessions ADD COLUMN connection_code TEXT NOT NULL DEFAULT 'ok';

UPDATE agent_sessions SET seq = (
    SELECT COUNT(*) FROM agent_sessions s2
    WHERE s2.registered_at < agent_sessions.registered_at
       OR (s2.registered_at = agent_sessions.registered_at AND s2.id <= agent_sessions.id)
);

CREATE UNIQUE INDEX IF NOT EXISTS agent_sessions_seq_idx ON agent_sessions (seq);
