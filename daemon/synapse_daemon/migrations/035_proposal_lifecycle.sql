-- Migration 035 -- Proposal backlog lifecycle + first-class categorization.
--
-- Replaces the overloaded open/approved/rejected status with two independent concepts:
--   lifecycle: proposed -> in_progress -> done
--   decision:  pending | accepted | declined
-- Existing approvals/rejections migrate to decision state only; they are NOT assumed implemented.
-- Lifecycle evidence is durable and inspectable so auto-detection never becomes a black box.
-- Never edit a shipped migration.
-- runner:foreign_keys=off

CREATE TABLE improvement_proposals_v2 (
    id                      TEXT PRIMARY KEY,
    title                   TEXT NOT NULL,
    rationale_md            TEXT NOT NULL DEFAULT '',
    project_id              TEXT REFERENCES projects(id) ON DELETE SET NULL,
    source_runtime          TEXT NOT NULL DEFAULT '',
    kind                    TEXT NOT NULL DEFAULT 'idea',
    est_effort              TEXT NOT NULL DEFAULT '',
    est_token_cost          INTEGER NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'proposed'
                                CHECK (status IN ('proposed', 'in_progress', 'done')),
    decision                TEXT NOT NULL DEFAULT 'pending'
                                CHECK (decision IN ('pending', 'accepted', 'declined')),
    resolution_note         TEXT NOT NULL DEFAULT '',
    lifecycle_source        TEXT NOT NULL DEFAULT '',
    lifecycle_evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    decision_at             TEXT,
    started_at              TEXT,
    done_at                 TEXT,
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);

INSERT INTO improvement_proposals_v2 (
    id, title, rationale_md, project_id, source_runtime, kind,
    est_effort, est_token_cost, status, decision, resolution_note,
    lifecycle_source, lifecycle_evidence_json,
    created_at, updated_at, decision_at, started_at, done_at, metadata_json
)
SELECT
    id,
    title,
    rationale_md,
    project_id,
    source_runtime,
    CASE lower(trim(CASE WHEN json_valid(metadata_json) THEN COALESCE(json_extract(metadata_json, '$.kind'), '') ELSE '' END))
        WHEN 'error' THEN 'bug'
        WHEN 'idea' THEN 'improvement'
        WHEN 'feature' THEN 'improvement'
        WHEN 'ui' THEN 'ui-ux'
        WHEN 'ux' THEN 'ui-ux'
        WHEN 'ui/ux' THEN 'ui-ux'
        WHEN 'perf' THEN 'performance'
        WHEN 'devex' THEN 'developer-experience'
        WHEN 'doc-drift' THEN 'docs'
        WHEN 'dedup' THEN 'maintenance'
        WHEN '' THEN 'improvement'
        ELSE lower(trim(json_extract(metadata_json, '$.kind')))
    END,
    est_effort,
    est_token_cost,
    'proposed',
    CASE status
        WHEN 'approved' THEN 'accepted'
        WHEN 'rejected' THEN 'declined'
        ELSE 'pending'
    END,
    resolution_note,
    'migration-035',
    '[]',
    created_at,
    updated_at,
    CASE WHEN status IN ('approved', 'rejected') THEN resolved_at ELSE NULL END,
    NULL,
    NULL,
    metadata_json
FROM improvement_proposals;

DROP TABLE improvement_proposals;
ALTER TABLE improvement_proposals_v2 RENAME TO improvement_proposals;

CREATE INDEX improvement_proposals_status_kind_idx
    ON improvement_proposals (status, kind, updated_at DESC);

CREATE INDEX improvement_proposals_decision_status_idx
    ON improvement_proposals (decision, status, updated_at DESC);

CREATE INDEX improvement_proposals_project_idx
    ON improvement_proposals (project_id, status, updated_at DESC);
