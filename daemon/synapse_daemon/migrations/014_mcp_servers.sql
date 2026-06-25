-- ADR-0017 (MW2): installed MCP servers the user's AI can use.
-- stdio servers are launched by the AI on demand; http servers run standalone
-- and Synapse can launch + health-check them.
CREATE TABLE IF NOT EXISTS mcp_servers (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    publisher       TEXT,
    description     TEXT NOT NULL DEFAULT '',
    transport       TEXT NOT NULL DEFAULT 'stdio' CHECK (transport IN ('stdio', 'http')),
    command         TEXT,
    args_json       TEXT NOT NULL DEFAULT '[]',
    url             TEXT,
    launch_command  TEXT,
    launch_args_json TEXT NOT NULL DEFAULT '[]',
    env_json        TEXT NOT NULL DEFAULT '{}',
    enabled         INTEGER NOT NULL DEFAULT 1,
    autorun         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
