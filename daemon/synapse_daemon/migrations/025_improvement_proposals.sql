-- Migration 025 -- Improvement proposals inbox (Plan 3 Phase 3f, ADR-0025).
--
-- Lets an AI file a *proposal* (an improvement idea) into the human review inbox
-- instead of acting on it unilaterally -- the safe "agents brainstorm, you
-- approve" path. You approve (accept the idea) or reject it. Surfaced alongside
-- work-item handoffs in GET /review/inbox. Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS improvement_proposals (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    rationale_md    TEXT NOT NULL DEFAULT '',
    project_id      TEXT REFERENCES projects(id) ON DELETE SET NULL,
    source_runtime  TEXT NOT NULL DEFAULT '',
    est_effort      TEXT NOT NULL DEFAULT '',
    est_token_cost  INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'approved', 'rejected')),
    resolution_note TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    resolved_at     TEXT,
    metadata_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS improvement_proposals_status_idx
    ON improvement_proposals (status, created_at DESC);
