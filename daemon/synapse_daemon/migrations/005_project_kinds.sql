-- Migration 005 -- project kinds (v0.1.19)
-- A 'kind' classifies what a project IS so the user can filter the Apps grid
-- and tell a UI app from an MCP server from a one-off script at a glance.
-- Discovery (synapse_daemon/discovery.py) populates it on import; the edit
-- dialog lets the user change it. Never edit a shipped migration.

-- Kinds (kept as a free string so future kinds drop in without a new migration):
--   'app'        -- generic launchable application (default)
--   'ui'         -- frontend / browser UI (Vite, Next, React, Astro, ...)
--   'service'    -- HTTP backend (FastAPI, Express, Django, ...)
--   'mcp-server' -- Model Context Protocol server (stdio or HTTP)
--   'library'    -- code package with no launch target
--   'script'     -- one-shot script
--   'other'      -- explicitly other; the user knows best
ALTER TABLE projects ADD COLUMN kind TEXT NOT NULL DEFAULT 'app';

CREATE INDEX IF NOT EXISTS projects_kind_idx ON projects (kind);
