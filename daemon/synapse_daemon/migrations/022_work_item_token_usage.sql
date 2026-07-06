-- Migration 022 -- Per-work-item token accounting (Plan 3 Phase 2, ADR-0025).
--
-- PTY squad workers report zero tokens today, so "fewer tokens than a
-- non-Synapse agent" is unprovable. This records each worker's self-reported
-- token usage (squad_id + role_id denormalized for a fast squad roll-up) using
-- the same provenance/source vocabulary as the benchmark engine, so squad and
-- benchmark efficiency speak one language. Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS work_item_token_usage (
    id                TEXT PRIMARY KEY,
    work_item_id      TEXT NOT NULL REFERENCES agent_work_items(id) ON DELETE CASCADE,
    squad_id          TEXT,
    role_id           TEXT,
    runtime_id        TEXT NOT NULL DEFAULT '',
    input_tokens      INTEGER NOT NULL DEFAULT 0,
    output_tokens     INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    token_provenance  TEXT NOT NULL DEFAULT 'reported',
    token_source      TEXT NOT NULL DEFAULT 'runtime_self_report',
    captured_at       TEXT NOT NULL,
    metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS work_item_token_usage_squad_idx
    ON work_item_token_usage (squad_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS work_item_token_usage_item_idx
    ON work_item_token_usage (work_item_id);
