-- Migration 016 -- AI Operating System advanced case engine + AI Factory
-- Durable case metadata, case graph lineage, case-owned jobs, and the native
-- AI Factory catalog for recipes/components/sources.
-- Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS ai_cases (
    id                    TEXT PRIMARY KEY,
    title                 TEXT NOT NULL DEFAULT '',
    primary_project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    case_mode             TEXT NOT NULL,
    mission_profile_id    TEXT,
    intent_json           TEXT NOT NULL DEFAULT '{}',
    targets_json          TEXT NOT NULL DEFAULT '{}',
    directives_json       TEXT NOT NULL DEFAULT '{}',
    policies_json         TEXT NOT NULL DEFAULT '{}',
    parent_case_id        TEXT REFERENCES ai_cases(id) ON DELETE SET NULL,
    root_case_id          TEXT,
    comparison_set_id     TEXT,
    candidate_label       TEXT,
    spawn_reason          TEXT,
    winning_child_case_id TEXT REFERENCES ai_cases(id) ON DELETE SET NULL,
    status                TEXT NOT NULL CHECK (status IN ('draft', 'running', 'stopped', 'completed', 'error')),
    phase                 TEXT NOT NULL CHECK (phase IN ('setup', 'orient', 'research', 'generate', 'compare', 'review', 'verify', 'handoff', 'stopped', 'error')),
    squad_id              TEXT REFERENCES agent_squads(id) ON DELETE SET NULL,
    lead_work_item_id     TEXT REFERENCES agent_work_items(id) ON DELETE SET NULL,
    lead_session_id       TEXT,
    branch_name           TEXT,
    worktree_path         TEXT,
    bundle_path           TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    started_at            TEXT,
    completed_at          TEXT,
    stopped_at            TEXT,
    last_error_code       TEXT,
    last_error_message    TEXT
);

CREATE INDEX IF NOT EXISTS ai_cases_primary_project_idx
    ON ai_cases (primary_project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ai_cases_status_idx
    ON ai_cases (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS ai_cases_root_idx
    ON ai_cases (root_case_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ai_cases_parent_idx
    ON ai_cases (parent_case_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_case_targets (
    case_id      TEXT NOT NULL REFERENCES ai_cases(id) ON DELETE CASCADE,
    project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    relation     TEXT NOT NULL CHECK (relation IN ('primary', 'neighbor', 'reference', 'integration')),
    created_at   TEXT NOT NULL,
    PRIMARY KEY (case_id, project_id, relation)
);

CREATE INDEX IF NOT EXISTS ai_case_targets_relation_idx
    ON ai_case_targets (case_id, relation, created_at);

CREATE TABLE IF NOT EXISTS ai_case_jobs (
    id                 TEXT PRIMARY KEY,
    case_id            TEXT NOT NULL REFERENCES ai_cases(id) ON DELETE CASCADE,
    phase              TEXT NOT NULL CHECK (phase IN ('setup', 'orient', 'research', 'generate', 'compare', 'review', 'verify', 'handoff', 'stopped', 'error')),
    label              TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('queued', 'starting', 'running', 'reviewing', 'testing', 'completed', 'failed', 'stopped')),
    worker_role_id     TEXT,
    runtime            TEXT,
    session_id         TEXT,
    cwd                TEXT,
    artifact_path      TEXT,
    transcript_file_id TEXT,
    notes_md           TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    started_at         TEXT,
    completed_at       TEXT,
    exit_code          INTEGER
);

CREATE INDEX IF NOT EXISTS ai_case_jobs_case_idx
    ON ai_case_jobs (case_id, created_at);

CREATE INDEX IF NOT EXISTS ai_case_jobs_session_idx
    ON ai_case_jobs (session_id);

CREATE TABLE IF NOT EXISTS ai_factory_components (
    id            TEXT PRIMARY KEY,
    family        TEXT NOT NULL,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    tags_json     TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    content_md    TEXT NOT NULL DEFAULT '',
    builtin       INTEGER NOT NULL DEFAULT 0,
    source_id     TEXT REFERENCES ai_factory_sources(id) ON DELETE SET NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ai_factory_components_family_idx
    ON ai_factory_components (family, builtin DESC, name);

CREATE TABLE IF NOT EXISTS ai_factory_recipes (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    archetype               TEXT NOT NULL,
    nav_model               TEXT NOT NULL,
    interaction_model       TEXT NOT NULL,
    visual_language         TEXT NOT NULL,
    data_behavior           TEXT NOT NULL,
    density_rule            TEXT NOT NULL,
    component_ids_json      TEXT NOT NULL DEFAULT '[]',
    default_directives_json TEXT NOT NULL DEFAULT '{}',
    tags_json               TEXT NOT NULL DEFAULT '[]',
    builtin                 INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ai_factory_recipes_archetype_idx
    ON ai_factory_recipes (archetype, builtin DESC, name);

CREATE TABLE IF NOT EXISTS ai_factory_sources (
    id                 TEXT PRIMARY KEY,
    label              TEXT NOT NULL,
    source_type        TEXT NOT NULL,
    url                TEXT,
    reuse_posture      TEXT NOT NULL,
    provenance_summary TEXT NOT NULL DEFAULT '',
    metadata_json      TEXT NOT NULL DEFAULT '{}',
    notes_md           TEXT NOT NULL DEFAULT '',
    builtin            INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ai_factory_sources_type_idx
    ON ai_factory_sources (source_type, updated_at DESC);
