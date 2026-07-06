-- Migration 024 -- Squad token budget (Plan 3 Phase 3, ADR-0025).
--
-- Bounds total recorded token spend for a squad; the work-item launch path
-- refuses to start a new worker once the budget is exhausted. 0 = no budget
-- (backward-compatible default). Pairs with the concurrency cap (023) and
-- per-work-item token accounting (022). Never edit a shipped migration.

ALTER TABLE agent_squads
    ADD COLUMN token_budget INTEGER NOT NULL DEFAULT 0;
