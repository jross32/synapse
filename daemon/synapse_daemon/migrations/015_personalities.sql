-- ADR-0018 (MW3): AI personalities. A worker = role + personality, so two
-- same-role AIs (e.g. two UI designers) can differ in voice + approach and
-- actually collaborate / debate when building.
CREATE TABLE IF NOT EXISTS personalities (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    blurb              TEXT NOT NULL DEFAULT '',
    traits_json        TEXT NOT NULL DEFAULT '[]',
    prompt_preamble_md TEXT NOT NULL DEFAULT '',
    voice              TEXT,
    builtin            INTEGER NOT NULL DEFAULT 0,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

-- A roster entry (work item) can carry a personality alongside its role.
ALTER TABLE agent_work_items ADD COLUMN personality_id TEXT;
