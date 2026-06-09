// Project workbench launcher (v0.1.29 · ADR-0002 Phase B).
//
// Spawns a PTY session pre-`cd`'d into the project's working directory,
// defaulting to the user's preferred coder (claude → codex → shell, picked
// daemon-side via shutil.which).

import { apiFetch } from './api-client';
import type { PtySessionSummary } from './generated-types';

export interface WorkbenchSession extends PtySessionSummary {
  project_id: string;
  project_name: string;
}

export interface OpenWorkbenchRequest {
  argv?: string[];
  rows?: number;
  cols?: number;
}

export async function openProjectWorkbench(
  projectId: string,
  body: OpenWorkbenchRequest = {}
): Promise<WorkbenchSession> {
  return apiFetch<WorkbenchSession>(
    `/projects/${encodeURIComponent(projectId)}/workbench`,
    { method: 'POST', body }
  );
}
