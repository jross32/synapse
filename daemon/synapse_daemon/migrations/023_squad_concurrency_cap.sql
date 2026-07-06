-- Migration 023 -- Squad concurrency cap (Plan 3 Phase 3, ADR-0025).
--
-- Bounds how many workers a squad may run at once, so an autonomous boss can't
-- thrash the machine by launching more workers than the box can handle.
-- 0 = no cap (backward-compatible default). Never edit a shipped migration.

ALTER TABLE agent_squads
    ADD COLUMN max_concurrent INTEGER NOT NULL DEFAULT 0;
