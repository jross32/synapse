-- AI-facing "how do I do X" procedures that live outside this codebase (e.g. driving a
-- third-party web UI). Steps are semantic ("click the button labeled Settings"), never pixel
-- coordinates, because coordinates rot the moment a layout shifts. status/status_note/
-- last_verified_at/verified_by let any executing AI report "this step no longer matches what's
-- on screen" instead of failing silently -- see playbooks.py record_verification().
CREATE TABLE IF NOT EXISTS playbooks (
    id                TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    summary           TEXT NOT NULL DEFAULT '',
    steps_json        TEXT NOT NULL DEFAULT '[]',
    status            TEXT NOT NULL DEFAULT 'healthy'
                          CHECK (status IN ('healthy', 'needs_attention', 'broken')),
    status_note       TEXT,
    last_verified_at  TEXT,
    verified_by       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
