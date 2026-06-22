-- Migration 010 -- Synapse Accounts profile refactor
-- Adds first-party account/profile fields while keeping existing local-first
-- profile, host, catalog, and service tables intact.

ALTER TABLE profile_state ADD COLUMN username TEXT;
ALTER TABLE profile_state ADD COLUMN email_verified_at TEXT;
ALTER TABLE profile_state ADD COLUMN preferences_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE profile_state ADD COLUMN preferences_updated_at TEXT;

