-- 045: persistent AI staff identities layered over existing role + personality workers.
CREATE TABLE IF NOT EXISTS staff_avatar_assets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    glyph TEXT NOT NULL,
    background TEXT NOT NULL,
    accent TEXT NOT NULL,
    builtin INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS staff_members (
    id TEXT PRIMARY KEY,
    handle TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    title TEXT NOT NULL,
    role_template_id TEXT NOT NULL REFERENCES agent_role_templates(id) ON DELETE RESTRICT,
    personality_id TEXT REFERENCES personalities(id) ON DELETE SET NULL,
    avatar_asset_id TEXT REFERENCES staff_avatar_assets(id) ON DELETE SET NULL,
    bio TEXT NOT NULL DEFAULT '',
    about_md TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'available'
        CHECK(status IN ('available','working','waiting_for_owner','blocked','offline')),
    status_line TEXT NOT NULL DEFAULT '',
    specialties_json TEXT NOT NULL DEFAULT '[]',
    goals_json TEXT NOT NULL DEFAULT '[]',
    assigned_project_ids_json TEXT NOT NULL DEFAULT '[]',
    authority_policy TEXT NOT NULL DEFAULT 'prepare_for_approval'
        CHECK(authority_policy IN ('advise_only','prepare_for_approval','act_within_limits')),
    notification_policy_json TEXT NOT NULL DEFAULT '{}',
    contact_channels_json TEXT NOT NULL DEFAULT '[]',
    builtin INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS staff_work_items (
    staff_member_id TEXT NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
    work_item_id TEXT NOT NULL REFERENCES agent_work_items(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (staff_member_id, work_item_id)
);

CREATE INDEX IF NOT EXISTS staff_members_role_idx ON staff_members(role_template_id, status);
CREATE INDEX IF NOT EXISTS staff_members_sort_idx ON staff_members(sort_order, display_name);
CREATE INDEX IF NOT EXISTS staff_work_items_staff_idx ON staff_work_items(staff_member_id, created_at DESC);
