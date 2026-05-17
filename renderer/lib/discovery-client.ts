// Typed REST client for project auto-discovery (v0.1.8.5).

import { apiFetch } from './api-client';
import type { DiscoveryScanResponse, ImportReport } from './generated-types';

/** Scan a folder for projects. `root` empty -> the daemon scans the home dir. */
export async function scanForProjects(root: string, depth = 2): Promise<DiscoveryScanResponse> {
  const params = new URLSearchParams({ depth: String(depth) });
  if (root.trim()) params.set('root', root.trim());
  return apiFetch<DiscoveryScanResponse>(`/discovery/scan?${params}`, { method: 'GET' });
}

export interface ImportItem {
  id: string;
  name: string;
  path: string;
  launch_cmd: string;
  description?: string | null;
  expected_port?: number | null;
  icon?: string | null;
  group?: string | null;
  tags?: string[];
}

/** Bulk-import the chosen detected projects (created with discovered=true). */
export async function importProjects(projects: ImportItem[]): Promise<ImportReport> {
  return apiFetch<ImportReport>('/discovery/import', {
    method: 'POST',
    body: { projects },
  });
}
