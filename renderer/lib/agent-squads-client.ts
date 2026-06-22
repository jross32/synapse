import { apiFetch } from './api-client';
import type {
  AgentRoleTemplate,
  AgentSquad,
  AgentSquadDetail,
  AgentSquadStatus,
  AgentWorkItem,
  AgentWorkItemStatus,
  PtySessionSummary,
} from './generated-types';

export interface AgentRoleTemplatesResponse {
  templates: AgentRoleTemplate[];
}

export interface AgentSquadsResponse {
  squads: AgentSquad[];
}

export interface CreateAgentSquadInput {
  project_id: string;
  name: string;
  goal_md?: string;
  status?: AgentSquadStatus;
  lead_role_id?: string | null;
}

export interface PatchAgentSquadInput {
  name?: string;
  goal_md?: string;
  status?: AgentSquadStatus;
  lead_role_id?: string | null;
}

export interface CreateAgentWorkItemInput {
  title: string;
  instructions_md?: string;
  assigned_role_id?: string | null;
  preferred_runtime?: string | null;
  parent_id?: string | null;
}

export interface LaunchAgentWorkItemInput {
  preferred_runtime?: string | null;
  rows?: number;
  cols?: number;
  open_in_tab?: boolean;
}

export interface DelegateAgentWorkItemInput {
  title: string;
  instructions_md?: string;
  assigned_role_id?: string | null;
  preferred_runtime?: string | null;
}

export interface HandoffAgentWorkItemInput {
  status?: AgentWorkItemStatus;
  summary_md: string;
  blockers_md?: string | null;
  files_touched?: string[];
  suggested_next_role?: string | null;
}

export interface UpdateAgentWorkItemStatusInput {
  status: AgentWorkItemStatus;
}

export interface AgentWorkItemLaunchResponse extends PtySessionSummary {
  squad_id: string;
  work_item_id: string;
  role_id: string;
  runtime: string;
  role_prompt_file: string;
  project_id: string;
  project_name: string;
}

export async function listAgentRoleTemplates(): Promise<AgentRoleTemplate[]> {
  const res = await apiFetch<AgentRoleTemplatesResponse>('/agent-role-templates', {
    method: 'GET',
  });
  return res.templates;
}

export async function listAgentSquads(): Promise<AgentSquad[]> {
  const res = await apiFetch<AgentSquadsResponse>('/agent-squads', { method: 'GET' });
  return res.squads;
}

export async function getAgentSquad(id: string): Promise<AgentSquadDetail> {
  return apiFetch<AgentSquadDetail>(`/agent-squads/${encodeURIComponent(id)}`, {
    method: 'GET',
  });
}

export async function createAgentSquad(
  input: CreateAgentSquadInput
): Promise<AgentSquad> {
  return apiFetch<AgentSquad>('/agent-squads', { method: 'POST', body: input });
}

export async function patchAgentSquad(
  id: string,
  patch: PatchAgentSquadInput
): Promise<AgentSquad> {
  return apiFetch<AgentSquad>(`/agent-squads/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: patch,
  });
}

export interface StopAgentSquadResponse {
  squad_id: string;
  stopped_sessions: number;
  work_item_ids: string[];
}

/** Kill switch: close every live PTY session owned by this squad. */
export async function stopAgentSquad(id: string): Promise<StopAgentSquadResponse> {
  return apiFetch<StopAgentSquadResponse>(`/agent-squads/${encodeURIComponent(id)}/stop`, {
    method: 'POST',
  });
}

export async function createAgentWorkItem(
  squadId: string,
  input: CreateAgentWorkItemInput
): Promise<AgentWorkItem> {
  return apiFetch<AgentWorkItem>(`/agent-squads/${encodeURIComponent(squadId)}/work-items`, {
    method: 'POST',
    body: input,
  });
}

export async function launchAgentWorkItem(
  workItemId: string,
  input: LaunchAgentWorkItemInput = {}
): Promise<AgentWorkItemLaunchResponse> {
  return apiFetch<AgentWorkItemLaunchResponse>(
    `/agent-work-items/${encodeURIComponent(workItemId)}/launch`,
    { method: 'POST', body: input }
  );
}

export async function delegateAgentWorkItem(
  workItemId: string,
  input: DelegateAgentWorkItemInput
): Promise<AgentWorkItem> {
  return apiFetch<AgentWorkItem>(`/agent-work-items/${encodeURIComponent(workItemId)}/delegate`, {
    method: 'POST',
    body: input,
  });
}

export async function handoffAgentWorkItem(
  workItemId: string,
  input: HandoffAgentWorkItemInput
): Promise<AgentWorkItem> {
  return apiFetch<AgentWorkItem>(`/agent-work-items/${encodeURIComponent(workItemId)}/handoff`, {
    method: 'POST',
    body: input,
  });
}

export async function updateAgentWorkItemStatus(
  workItemId: string,
  input: UpdateAgentWorkItemStatusInput
): Promise<AgentWorkItem> {
  return apiFetch<AgentWorkItem>(`/agent-work-items/${encodeURIComponent(workItemId)}/status`, {
    method: 'POST',
    body: input,
  });
}
