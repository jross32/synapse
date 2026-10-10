-- 046: advanced AI staff operating layer.
CREATE TABLE IF NOT EXISTS staff_responsibilities (
    id TEXT PRIMARY KEY,
    staff_member_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('high','medium','low')),
    cadence TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staff_responsibilities_staff_idx
    ON staff_responsibilities(staff_member_id, enabled, sort_order);

CREATE TABLE IF NOT EXISTS staff_kpis (
    id TEXT PRIMARY KEY,
    staff_member_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL DEFAULT 'increase' CHECK(direction IN ('increase','decrease','range','maintain')),
    target_value REAL,
    target_min REAL,
    target_max REAL,
    current_value REAL,
    status TEXT NOT NULL DEFAULT 'unknown' CHECK(status IN ('unknown','on_track','watch','off_track')),
    source TEXT NOT NULL DEFAULT 'manual',
    period TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staff_kpis_staff_idx
    ON staff_kpis(staff_member_id, status, sort_order);

CREATE TABLE IF NOT EXISTS staff_memories (
    id TEXT PRIMARY KEY,
    staff_member_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'observation'
        CHECK(kind IN ('profile','decision','lesson','preference','observation')),
    title TEXT NOT NULL,
    body_md TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    importance INTEGER NOT NULL DEFAULT 3 CHECK(importance BETWEEN 1 AND 5),
    pinned INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'owner',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staff_memories_staff_idx
    ON staff_memories(staff_member_id, pinned DESC, importance DESC, updated_at DESC);

CREATE TABLE IF NOT EXISTS staff_permissions (
    id TEXT PRIMARY KEY,
    staff_member_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    capability TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('allow','ask','deny')),
    limits_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(staff_member_id, scope_type, scope_id, capability)
);
CREATE INDEX IF NOT EXISTS staff_permissions_staff_idx
    ON staff_permissions(staff_member_id, scope_type, decision);

CREATE TABLE IF NOT EXISTS staff_triggers (
    id TEXT PRIMARY KEY,
    staff_member_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    trigger_type TEXT NOT NULL CHECK(trigger_type IN ('schedule','event','condition')),
    config_json TEXT NOT NULL DEFAULT '{}',
    prompt_md TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 0,
    last_run_at TEXT,
    next_run_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staff_triggers_staff_idx
    ON staff_triggers(staff_member_id, enabled, trigger_type);

CREATE TABLE IF NOT EXISTS staff_channel_connections (
    id TEXT PRIMARY KEY,
    staff_member_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'disconnected'
        CHECK(status IN ('connected','disconnected','error')),
    account_label TEXT,
    external_id TEXT,
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(staff_member_id, channel)
);
CREATE INDEX IF NOT EXISTS staff_channels_staff_idx
    ON staff_channel_connections(staff_member_id, status);

CREATE TABLE IF NOT EXISTS staff_relationships (
    from_staff_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    to_staff_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(from_staff_id, to_staff_id, relationship)
);

CREATE TABLE IF NOT EXISTS staff_events (
    id TEXT PRIMARY KEY,
    staff_member_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body_md TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info' CHECK(severity IN ('info','success','warning','critical')),
    action_required INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'system',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staff_events_staff_idx
    ON staff_events(staff_member_id, created_at DESC);
CREATE INDEX IF NOT EXISTS staff_events_action_idx
    ON staff_events(action_required, severity, created_at DESC);
