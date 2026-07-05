-- Migration 019 -- Synapse Quality OS + UI contract registry.
-- Adds durable quality gates, browser-proof evidence, surface mapping,
-- and contract records that multiple AI runtimes can share.
-- Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS ui_surface_map (
    id                     TEXT PRIMARY KEY,
    title                  TEXT NOT NULL,
    route                  TEXT NOT NULL DEFAULT '',
    description            TEXT NOT NULL DEFAULT '',
    action_ids_json        TEXT NOT NULL DEFAULT '[]',
    file_patterns_json     TEXT NOT NULL DEFAULT '[]',
    linked_surface_ids_json TEXT NOT NULL DEFAULT '[]',
    metadata_json          TEXT NOT NULL DEFAULT '{}',
    builtin                INTEGER NOT NULL DEFAULT 0,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ui_surface_map_route_idx
    ON ui_surface_map (route, builtin DESC, title);

CREATE TABLE IF NOT EXISTS ui_contracts (
    id                       TEXT PRIMARY KEY,
    title                    TEXT NOT NULL,
    surface_id               TEXT NOT NULL REFERENCES ui_surface_map(id) ON DELETE CASCADE,
    severity                 TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    route                    TEXT NOT NULL DEFAULT '',
    action_id                TEXT,
    preconditions_json       TEXT NOT NULL DEFAULT '[]',
    steps_json               TEXT NOT NULL DEFAULT '[]',
    assertions_json          TEXT NOT NULL DEFAULT '[]',
    touched_file_patterns_json TEXT NOT NULL DEFAULT '[]',
    linked_surface_ids_json  TEXT NOT NULL DEFAULT '[]',
    latest_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    metadata_json            TEXT NOT NULL DEFAULT '{}',
    builtin                  INTEGER NOT NULL DEFAULT 0,
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ui_contracts_surface_idx
    ON ui_contracts (surface_id, severity, builtin DESC, title);

CREATE TABLE IF NOT EXISTS quality_gates (
    id                      TEXT PRIMARY KEY,
    subject_type            TEXT NOT NULL,
    subject_id              TEXT NOT NULL,
    gate_kind               TEXT NOT NULL,
    title                   TEXT NOT NULL DEFAULT '',
    blocking                INTEGER NOT NULL DEFAULT 1,
    status                  TEXT NOT NULL CHECK (status IN ('open', 'passed', 'failed', 'waived')),
    required_evidence_json  TEXT NOT NULL DEFAULT '[]',
    linked_surface_ids_json TEXT NOT NULL DEFAULT '[]',
    linked_contract_ids_json TEXT NOT NULL DEFAULT '[]',
    waiver_state            TEXT NOT NULL CHECK (waiver_state IN ('none', 'requested', 'waived')),
    opened_at               TEXT NOT NULL,
    resolved_at             TEXT,
    resolved_by             TEXT,
    audit_details_json      TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS quality_gates_subject_idx
    ON quality_gates (subject_type, subject_id, status, blocking);

CREATE INDEX IF NOT EXISTS quality_gates_kind_idx
    ON quality_gates (gate_kind, status, opened_at DESC);

CREATE TABLE IF NOT EXISTS quality_evidence (
    id              TEXT PRIMARY KEY,
    subject_type    TEXT NOT NULL,
    subject_id      TEXT NOT NULL,
    gate_id         TEXT REFERENCES quality_gates(id) ON DELETE SET NULL,
    contract_id     TEXT REFERENCES ui_contracts(id) ON DELETE SET NULL,
    evidence_kind   TEXT NOT NULL,
    label           TEXT NOT NULL DEFAULT '',
    surface_id      TEXT REFERENCES ui_surface_map(id) ON DELETE SET NULL,
    route           TEXT NOT NULL DEFAULT '',
    action_id       TEXT,
    selector        TEXT,
    verdict         TEXT NOT NULL CHECK (verdict IN ('pass', 'fail', 'info')),
    artifact_path   TEXT,
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS quality_evidence_subject_idx
    ON quality_evidence (subject_type, subject_id, created_at DESC);

CREATE INDEX IF NOT EXISTS quality_evidence_gate_idx
    ON quality_evidence (gate_id, created_at DESC);

CREATE INDEX IF NOT EXISTS quality_evidence_contract_idx
    ON quality_evidence (contract_id, created_at DESC);

ALTER TABLE agent_work_items
    ADD COLUMN verdict_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE coder_review_passes
    ADD COLUMN verdict_json TEXT NOT NULL DEFAULT '{}';
