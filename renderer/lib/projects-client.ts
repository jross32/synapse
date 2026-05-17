// Typed REST client for the projects endpoints (Milestone D).
//
// One thin function per endpoint defined in docs/api-changes.md. Errors
// surface as `SynapseApiError` carrying an `ErrorEnvelope` (Contract #4).

import { apiFetch } from './api-client';
import type {
  Project,
  ProjectListResponse,
  ProjectUpdate,
} from './generated-types';

export type AuditSource = 'desktop' | 'mobile' | 'tray' | 'cli' | 'auto';

export async function listProjects(): Promise<Project[]> {
  const res = await apiFetch<ProjectListResponse>('/projects', { method: 'GET' });
  return res.projects;
}

export async function getProject(id: string): Promise<Project> {
  return apiFetch<Project>(`/projects/${encodeURIComponent(id)}`, { method: 'GET' });
}

/** The fields a user supplies when creating a project; the daemon fills the rest. */
export interface ProjectCreateInput {
  id: string;
  name: string;
  path: string;
  launch_cmd: string;
  description?: string | null;
  category?: string | null;
  icon?: string | null;
  expected_port?: number | null;
  group?: string | null;
}

export async function createProject(input: ProjectCreateInput): Promise<Project> {
  return apiFetch<Project>('/projects', { method: 'POST', body: input });
}

/** Fetch the tail of a project's most recent log file (Contract #3). */
export interface ProjectLogs {
  project_id: string;
  log_path: string | null;
  lines: string[];
  total_lines: number;
}

export async function getProjectLogs(id: string, lines = 200): Promise<ProjectLogs> {
  const params = new URLSearchParams({ lines: String(lines) });
  return apiFetch<ProjectLogs>(`/projects/${encodeURIComponent(id)}/logs?${params}`, {
    method: 'GET',
  });
}

export async function patchProject(id: string, patch: ProjectUpdate): Promise<Project> {
  return apiFetch<Project>(`/projects/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: patch,
  });
}

export async function deleteProject(id: string): Promise<void> {
  await apiFetch<void>(`/projects/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function launchProject(id: string, source: AuditSource = 'desktop'): Promise<Project> {
  return apiFetch<Project>(`/projects/${encodeURIComponent(id)}/launch`, {
    method: 'POST',
    body: { source },
  });
}

export async function stopProject(id: string, source: AuditSource = 'desktop'): Promise<Project> {
  return apiFetch<Project>(`/projects/${encodeURIComponent(id)}/stop`, {
    method: 'POST',
    body: { source },
  });
}
