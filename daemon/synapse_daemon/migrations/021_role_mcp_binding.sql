-- Migration 021 -- Per-role MCP server binding (Plan 3 Phase 1, ADR-0025).
--
-- Lets a role scope which MCP servers its workers receive, instead of every
-- Claude worker getting every enabled server (a token cost + attack surface).
-- Semantics of mcp_server_ids_json:
--   NULL      -> inherit ALL enabled servers (backward-compatible default)
--   '[]'      -> NO servers (token-lean roles that never touch a browser/tool)
--   '["id"]'  -> only those servers (e.g. a browser role gets just playwright)
-- Never edit a shipped migration.

ALTER TABLE agent_role_templates
    ADD COLUMN mcp_server_ids_json TEXT DEFAULT NULL;
