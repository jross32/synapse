-- Migration 011 -- squad role hierarchy tiers (boss / supervisor / worker)
-- v0.1.36-dev follow-up. Adds role_tier so the Team Builder can group roles
-- and model a boss -> supervisor -> worker structure. The tier is validated by
-- the Pydantic AgentRoleTier enum at the app layer (SQLite ALTER TABLE cannot
-- add a CHECK constraint after the fact). Never edit a shipped migration.

ALTER TABLE agent_role_templates ADD COLUMN role_tier TEXT NOT NULL DEFAULT 'worker';

-- Tier the roles seeded by migration 008 so existing installs gain the
-- hierarchy without a reset. New seeds carry their own tier on insert.
UPDATE agent_role_templates SET role_tier = 'boss' WHERE id = 'planner';
UPDATE agent_role_templates SET role_tier = 'worker'
    WHERE id IN ('implementer', 'reviewer', 'researcher');
