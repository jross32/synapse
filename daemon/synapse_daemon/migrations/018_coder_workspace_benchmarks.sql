-- Coder Workspace + benchmark foundation.
--
-- Durable thread-first workspace records plus benchmark specs/runs/attempts.

CREATE TABLE IF NOT EXISTS coder_workspace_preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    advanced_terminal_enabled INTEGER NOT NULL DEFAULT 0,
    raw_pty_enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coder_threads (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    active_runtime_id TEXT,
    active_provider TEXT,
    active_model TEXT,
    workspace_context_mode TEXT NOT NULL DEFAULT 'project',
    pinned INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    thread_kind TEXT NOT NULL DEFAULT 'chat',
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_message_at TEXT,
    last_run_at TEXT
);

CREATE INDEX IF NOT EXISTS coder_threads_project_recent_idx
    ON coder_threads (project_id, archived, pinned DESC, updated_at DESC);

CREATE TABLE IF NOT EXISTS coder_messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES coder_threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content_md TEXT NOT NULL DEFAULT '',
    runtime_id TEXT,
    provider TEXT,
    model TEXT,
    coder_run_id TEXT,
    artifact_ids_json TEXT,
    usage_summary_json TEXT,
    benchmark_attempt_id TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS coder_messages_thread_idx
    ON coder_messages (thread_id, created_at);

CREATE TABLE IF NOT EXISTS coder_runtime_switches (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES coder_threads(id) ON DELETE CASCADE,
    from_runtime_id TEXT,
    from_provider TEXT,
    from_model TEXT,
    to_runtime_id TEXT,
    to_provider TEXT,
    to_model TEXT,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS coder_runtime_switches_thread_idx
    ON coder_runtime_switches (thread_id, created_at);

CREATE TABLE IF NOT EXISTS coder_review_passes (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES coder_threads(id) ON DELETE CASCADE,
    requested_runtime_id TEXT,
    requested_provider TEXT,
    requested_model TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    title TEXT NOT NULL DEFAULT 'Review pass',
    summary_md TEXT NOT NULL DEFAULT '',
    coder_run_id TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS coder_review_passes_thread_idx
    ON coder_review_passes (thread_id, created_at);

CREATE TABLE IF NOT EXISTS coder_runs (
    id TEXT PRIMARY KEY,
    thread_id TEXT REFERENCES coder_threads(id) ON DELETE CASCADE,
    message_id TEXT REFERENCES coder_messages(id) ON DELETE SET NULL,
    review_pass_id TEXT REFERENCES coder_review_passes(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    pty_session_id TEXT,
    benchmark_attempt_id TEXT,
    runtime_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    surface_kind TEXT NOT NULL,
    surface_profile_version TEXT NOT NULL DEFAULT '',
    workspace_context_mode TEXT NOT NULL DEFAULT 'project',
    attachments_count INTEGER NOT NULL DEFAULT 0,
    hidden_context_hash TEXT,
    workspace_overhead_bytes INTEGER NOT NULL DEFAULT 0,
    context_items_injected INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'created',
    started_at TEXT NOT NULL,
    first_input_at TEXT,
    first_output_at TEXT,
    ended_at TEXT,
    exit_code INTEGER,
    input_event_count INTEGER NOT NULL DEFAULT 0,
    output_event_count INTEGER NOT NULL DEFAULT 0,
    used_any_input INTEGER NOT NULL DEFAULT 0,
    used_any_output INTEGER NOT NULL DEFAULT 0,
    crash_reason TEXT,
    metadata_json TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS coder_runs_pty_session_idx
    ON coder_runs (pty_session_id)
    WHERE pty_session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS coder_runs_thread_recent_idx
    ON coder_runs (thread_id, started_at DESC);

CREATE TABLE IF NOT EXISTS benchmark_specs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    primary_surface TEXT NOT NULL DEFAULT 'synapse_coder_thread',
    default_repeat_count INTEGER NOT NULL DEFAULT 3,
    official_weight_quality REAL NOT NULL DEFAULT 70.0,
    official_weight_efficiency REAL NOT NULL DEFAULT 20.0,
    official_weight_speed REAL NOT NULL DEFAULT 10.0,
    strict_comparable_policy TEXT NOT NULL DEFAULT 'matching-provenance',
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark_scenarios (
    id TEXT PRIMARY KEY,
    spec_id TEXT NOT NULL REFERENCES benchmark_specs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT 'v1',
    prompt_md TEXT NOT NULL DEFAULT '',
    artifact_contract_json TEXT,
    verifier_contract_json TEXT,
    rubric_contract_json TEXT,
    reset_procedure_md TEXT NOT NULL DEFAULT '',
    time_budget_seconds INTEGER NOT NULL DEFAULT 900,
    objective_weight REAL NOT NULL DEFAULT 60.0,
    rubric_weight REAL NOT NULL DEFAULT 40.0,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS benchmark_scenarios_spec_idx
    ON benchmark_scenarios (spec_id, name);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id TEXT PRIMARY KEY,
    spec_id TEXT NOT NULL REFERENCES benchmark_specs(id) ON DELETE RESTRICT,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    execution_mode TEXT NOT NULL DEFAULT 'serial',
    repeat_count INTEGER NOT NULL DEFAULT 3,
    notes_md TEXT NOT NULL DEFAULT '',
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    launched_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS benchmark_runs_spec_recent_idx
    ON benchmark_runs (spec_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS benchmark_attempts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    scenario_id TEXT NOT NULL REFERENCES benchmark_scenarios(id) ON DELETE RESTRICT,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    thread_id TEXT REFERENCES coder_threads(id) ON DELETE SET NULL,
    coder_run_id TEXT REFERENCES coder_runs(id) ON DELETE SET NULL,
    repeat_index INTEGER NOT NULL DEFAULT 1,
    candidate_group_key TEXT NOT NULL DEFAULT '',
    intended_runtime_id TEXT NOT NULL DEFAULT '',
    actual_runtime_id TEXT,
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    runtime_version TEXT,
    surface_kind TEXT NOT NULL,
    surface_profile_version TEXT NOT NULL DEFAULT '',
    workspace_context_mode TEXT NOT NULL DEFAULT 'project',
    attachments_count INTEGER NOT NULL DEFAULT 0,
    hidden_context_hash TEXT,
    workspace_context_hash TEXT,
    workspace_overhead_bytes INTEGER NOT NULL DEFAULT 0,
    context_items_injected INTEGER NOT NULL DEFAULT 0,
    scenario_version TEXT NOT NULL DEFAULT 'v1',
    prompt_hash TEXT,
    env_fingerprint_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    failure_code TEXT,
    failure_message TEXT,
    exit_code INTEGER,
    started_at TEXT,
    ended_at TEXT,
    elapsed_seconds REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    token_provenance TEXT NOT NULL DEFAULT 'unknown',
    token_source TEXT NOT NULL DEFAULT 'unavailable',
    quality_score_100 REAL,
    objective_pass_rate REAL,
    rubric_score_100 REAL,
    quality_per_1k_tokens REAL,
    quality_per_minute REAL,
    tokens_per_passed_check REAL,
    verifier_summary_json TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS benchmark_attempts_run_idx
    ON benchmark_attempts (run_id, scenario_id, repeat_index);

CREATE INDEX IF NOT EXISTS benchmark_attempts_group_idx
    ON benchmark_attempts (candidate_group_key, scenario_id, intended_runtime_id);

CREATE TABLE IF NOT EXISTS benchmark_artifacts (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES benchmark_attempts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL,
    mime TEXT NOT NULL DEFAULT 'application/octet-stream',
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS benchmark_artifacts_attempt_idx
    ON benchmark_artifacts (attempt_id, kind, created_at);
