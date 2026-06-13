-- Migration 006 -- project files (ADR-0003 Phase A + D, v0.1.30)
-- The single index for files the user uploads, transcripts persisted from
-- Sessions tabs, and chats imported from ChatGPT exports. The schema is
-- locked by ADR-0003's "Detailed design"; this migration is the canonical
-- implementation of that block. Never edit a shipped migration.

-- Per-file identity, location on disk, integrity hash, source and the AV
-- result. The same table backs:
--   * uploads from the project Files panel (source='upload')
--   * PTY scrollback persisted on workbench session exit (source='transcript')
--   * conversations imported from a ChatGPT export.zip (source='chatgpt-import')
--
-- NULL project_id is the *shared* workspace (see the 'shared' surfaces at
-- /api/v1/files and the SYNAPSE_SHARED_FILES env handed to sessions).
--
-- duplicate_of points at the file_id whose on-disk bytes we actually share
-- when an upload matches an existing sha256 (reference counting -- see the
-- "Dangling duplicate_of" decision in the ADR's test pass section).
CREATE TABLE IF NOT EXISTS project_files (
  id             TEXT PRIMARY KEY,
  project_id     TEXT,
  original_name  TEXT NOT NULL,
  on_disk_name   TEXT NOT NULL,
  mime           TEXT NOT NULL,
  size_bytes     INTEGER NOT NULL,
  sha256         TEXT NOT NULL,
  source         TEXT NOT NULL CHECK (source IN ('upload', 'transcript', 'chatgpt-import')),
  source_session TEXT,
  uploaded_at    TEXT NOT NULL,
  deleted_at     TEXT,
  scan_result    TEXT CHECK (scan_result IS NULL OR scan_result IN ('clean', 'blocked', 'unavailable')),
  scan_engine    TEXT,
  duplicate_of   TEXT,
  FOREIGN KEY (project_id) REFERENCES projects (id),
  FOREIGN KEY (duplicate_of) REFERENCES project_files (id)
);

-- "List files for project X" + "list all shared files" need fast lookups
-- and they're always filtered on deleted_at IS NULL.
CREATE INDEX IF NOT EXISTS project_files_project_idx
  ON project_files (project_id) WHERE deleted_at IS NULL;

-- Concurrent-upload dedup (issue #2 in the ADR test pass) does a
-- SELECT ... WHERE sha256 = ?. Hot path -- needs the index.
CREATE INDEX IF NOT EXISTS project_files_sha256_idx
  ON project_files (sha256);

-- Soft delete with promotion (issue #3) walks rows that reference a deleted
-- canonical via duplicate_of. Only a small fraction of rows are duplicates
-- so a partial index keeps the index tiny.
CREATE INDEX IF NOT EXISTS project_files_duplicate_of_idx
  ON project_files (duplicate_of) WHERE duplicate_of IS NOT NULL;
