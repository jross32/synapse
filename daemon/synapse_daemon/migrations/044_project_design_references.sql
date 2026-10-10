-- 044: semantic project design references layered over durable project_files.
CREATE TABLE project_design_references (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  file_id TEXT NOT NULL REFERENCES project_files(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('proposed_ui','reference','brand','flow','architecture','other')),
  title TEXT NOT NULL,
  description TEXT,
  is_current INTEGER NOT NULL DEFAULT 0,
  ai_visible INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX project_design_refs_project_idx ON project_design_references(project_id, role, is_current);
CREATE UNIQUE INDEX project_design_refs_file_role_idx ON project_design_references(file_id, role);
