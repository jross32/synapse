-- Migration 003 -- project discovery + groups + pinning
-- Synapse v0.1.8.5. Adds the columns behind auto-discovery and the
-- groups / pinning organisation features. Never edit a shipped migration.

-- Where the project came from: 1 = imported via auto-discovery, 0 = added by hand.
ALTER TABLE projects ADD COLUMN discovered INTEGER NOT NULL DEFAULT 0;

-- Pinned projects float to the top of the Apps grid + feed the Home slideshow.
ALTER TABLE projects ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;

-- Optional single group ("AI", "Scraping", "Games", ...). NULL = ungrouped.
ALTER TABLE projects ADD COLUMN group_name TEXT;

-- Free-form tags, stored as a JSON array of strings. Default '[]'.
ALTER TABLE projects ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]';

CREATE INDEX IF NOT EXISTS projects_group_idx ON projects (group_name);
CREATE INDEX IF NOT EXISTS projects_pinned_idx ON projects (pinned) WHERE pinned = 1;
