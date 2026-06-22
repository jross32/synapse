// Client for per-project decision records, backlog, and versions (ADR-0011).
// Types mirror daemon/synapse_daemon/project_records.py (gen-types is still a
// scaffold, so these are hand-maintained until it activates).

import { apiFetch } from './api-client';

export type ProjectAdrStatus =
  | 'idea'
  | 'draft'
  | 'proposed'
  | 'accepted'
  | 'rejected'
  | 'superseded';

export type ProjectBacklogStatus = 'todo' | 'in_progress' | 'done' | 'wontfix';
export type ProjectBacklogPriority = 'low' | 'medium' | 'high';

export interface ProjectAdr {
  id: string;
  project_id: string;
  number: number | null;
  title: string;
  status: ProjectAdrStatus;
  body_md: string;
  tags: string[];
  supersedes_id: string | null;
  source: string;
  created_at: string;
  updated_at: string;
  decided_at: string | null;
}

export interface ProjectBacklogItem {
  id: string;
  project_id: string;
  title: string;
  body_md: string;
  status: ProjectBacklogStatus;
  priority: ProjectBacklogPriority;
  order_index: number;
  source: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ProjectVersion {
  id: string;
  project_id: string;
  version: string;
  released_at: string | null;
  changes_md: string;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectRecords {
  project_id: string;
  adrs: ProjectAdr[];
  backlog: ProjectBacklogItem[];
  versions: ProjectVersion[];
}

const p = encodeURIComponent;

export function getProjectRecords(projectId: string): Promise<ProjectRecords> {
  return apiFetch<ProjectRecords>(`/projects/${p(projectId)}/records`, { method: 'GET' });
}

// ── ADRs ─────────────────────────────────────────────────────────────────────

export interface CreateAdrInput {
  title: string;
  status?: ProjectAdrStatus;
  body_md?: string;
  tags?: string[];
  supersedes_id?: string | null;
}

export interface UpdateAdrInput {
  title?: string;
  status?: ProjectAdrStatus;
  body_md?: string;
  tags?: string[];
  supersedes_id?: string | null;
}

export function createAdr(projectId: string, input: CreateAdrInput): Promise<ProjectAdr> {
  return apiFetch<ProjectAdr>(`/projects/${p(projectId)}/adrs`, { method: 'POST', body: input });
}

export function updateAdr(adrId: string, input: UpdateAdrInput): Promise<ProjectAdr> {
  return apiFetch<ProjectAdr>(`/project-adrs/${p(adrId)}`, { method: 'PATCH', body: input });
}

export function deleteAdr(adrId: string): Promise<void> {
  return apiFetch<void>(`/project-adrs/${p(adrId)}`, { method: 'DELETE' });
}

export function promoteAdr(adrId: string): Promise<ProjectAdr> {
  return apiFetch<ProjectAdr>(`/project-adrs/${p(adrId)}/promote`, { method: 'POST' });
}

// ── Backlog ──────────────────────────────────────────────────────────────────

export interface CreateBacklogInput {
  title: string;
  body_md?: string;
  status?: ProjectBacklogStatus;
  priority?: ProjectBacklogPriority;
  order_index?: number;
}

export interface UpdateBacklogInput {
  title?: string;
  body_md?: string;
  status?: ProjectBacklogStatus;
  priority?: ProjectBacklogPriority;
  order_index?: number;
}

export function createBacklogItem(
  projectId: string,
  input: CreateBacklogInput
): Promise<ProjectBacklogItem> {
  return apiFetch<ProjectBacklogItem>(`/projects/${p(projectId)}/backlog`, {
    method: 'POST',
    body: input,
  });
}

export function updateBacklogItem(
  itemId: string,
  input: UpdateBacklogInput
): Promise<ProjectBacklogItem> {
  return apiFetch<ProjectBacklogItem>(`/project-backlog/${p(itemId)}`, {
    method: 'PATCH',
    body: input,
  });
}

export function deleteBacklogItem(itemId: string): Promise<void> {
  return apiFetch<void>(`/project-backlog/${p(itemId)}`, { method: 'DELETE' });
}

// ── Versions ─────────────────────────────────────────────────────────────────

export interface CreateVersionInput {
  version: string;
  released_at?: string | null;
  changes_md?: string;
}

export interface UpdateVersionInput {
  version?: string;
  released_at?: string | null;
  changes_md?: string;
}

export function createVersion(
  projectId: string,
  input: CreateVersionInput
): Promise<ProjectVersion> {
  return apiFetch<ProjectVersion>(`/projects/${p(projectId)}/versions`, {
    method: 'POST',
    body: input,
  });
}

export function updateVersion(
  versionId: string,
  input: UpdateVersionInput
): Promise<ProjectVersion> {
  return apiFetch<ProjectVersion>(`/project-versions/${p(versionId)}`, {
    method: 'PATCH',
    body: input,
  });
}

export function deleteVersion(versionId: string): Promise<void> {
  return apiFetch<void>(`/project-versions/${p(versionId)}`, { method: 'DELETE' });
}
