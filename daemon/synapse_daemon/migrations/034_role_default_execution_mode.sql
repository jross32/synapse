-- Migration 034 -- Per-role default execution mode (ADR-0025 follow-up).
--
-- A role can opt its workers into "automatic" (headless, prompt-driven) launch by default
-- instead of "interactive" (an idle TUI a human drives by hand). NULL preserves today's
-- behavior exactly: a role with no explicit default still launches interactive unless a
-- caller overrides per-launch. This is what makes per-worker token accounting provable for
-- roles that opt in -- automatic mode is the one already wired end to end to the usage
-- parser (coder_runtimes.headless_argv + ai_executions.finalize_pty_execution); nothing
-- about that pipeline is new here, only a way to reach it without a caller having to
-- remember the flag on every launch.
-- Never edit a shipped migration.

ALTER TABLE agent_role_templates
    ADD COLUMN default_execution_mode TEXT DEFAULT NULL;
