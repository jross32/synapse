-- 043: account-scoped Synapse machine fleet.
-- A machine is an installable Synapse host, distinct from a paired browser/phone.
-- Stable machine IDs are generated locally and may later be associated with a
-- cloud account/control plane. Never store raw connector credentials here.
CREATE TABLE synapse_machines (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    platform TEXT NOT NULL,
    architecture TEXT NOT NULL,
    hostname TEXT NOT NULL,
    synapse_version TEXT,
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS synapse_machines_seen_idx
    ON synapse_machines(last_seen_at) WHERE revoked = 0;
