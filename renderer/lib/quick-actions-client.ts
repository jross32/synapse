// Typed REST client for the AI quick-actions endpoints (ADR-0003 Phase F · v0.1.34).
//
// One curated AI prompt per template; clicking a tile launches a workbench
// PTY in the auto-created 'scratch' project with the prompt pre-loaded so
// the Claude/Codex session sees it on prompt 1.

import { apiFetch } from './api-client';

export interface QuickAction {
  id: string;
  name: string;
  description: string;
  prompt: string;
  icon: string | null;
  default_argv: string[];
}

export interface QuickActionsList {
  actions: QuickAction[];
}

export interface QuickActionLaunchResponse {
  session_id: string;
  pid: number;
  cwd: string;
  argv: string[];
  project_id: string;
  project_name: string;
  action_id: string;
  action_name: string;
  prompt_file: string;
}

export async function listQuickActions(): Promise<QuickAction[]> {
  const res = await apiFetch<QuickActionsList>('/quick-actions', { method: 'GET' });
  return res.actions;
}

export interface QuickActionLaunchOptions {
  argv?: string[];
  rows?: number;
  cols?: number;
}

export async function launchQuickAction(
  actionId: string,
  opts: QuickActionLaunchOptions = {}
): Promise<QuickActionLaunchResponse> {
  return apiFetch<QuickActionLaunchResponse>(
    `/quick-actions/${encodeURIComponent(actionId)}/launch`,
    { method: 'POST', body: opts }
  );
}
