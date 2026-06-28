-- Migration 017 -- AI-first bundle installs for Marketplace + AI Factory.
-- Stores installed bundle manifests plus the concrete assets they own so
-- install/uninstall can stay deterministic.
-- Never edit a shipped migration.

CREATE TABLE IF NOT EXISTS ai_bundle_installs (
    bundle_id      TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    publisher      TEXT NOT NULL,
    version        TEXT NOT NULL,
    source         TEXT NOT NULL DEFAULT 'marketplace',
    manifest_json  TEXT NOT NULL,
    installed_at   TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ai_bundle_installs_updated_idx
    ON ai_bundle_installs (updated_at DESC);

CREATE TABLE IF NOT EXISTS ai_bundle_assets (
    bundle_id    TEXT NOT NULL REFERENCES ai_bundle_installs(bundle_id) ON DELETE CASCADE,
    asset_kind   TEXT NOT NULL,
    asset_id     TEXT NOT NULL,
    label        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    PRIMARY KEY (bundle_id, asset_kind, asset_id)
);

CREATE INDEX IF NOT EXISTS ai_bundle_assets_lookup_idx
    ON ai_bundle_assets (asset_kind, asset_id, bundle_id);
