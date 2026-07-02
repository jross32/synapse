import { apiFetch } from './api-client';
import type {
  CoderMessage,
  CoderReviewPass,
  CoderRun,
  CoderThread,
  CoderThreadDetail,
  CoderThreadSummary,
  CoderWorkspaceContext,
  CoderWorkspacePreferences,
  PtySessionSummary,
} from './generated-types';

const p = encodeURIComponent;

export interface CoderThreadCreateInput {
  title?: string;
  active_runtime_id?: string | null;
  active_provider?: string | null;
  active_model?: string | null;
  workspace_context_mode?: string;
  pinned?: boolean;
  archived?: boolean;
  thread_kind?: string;
  metadata?: Record<string, unknown>;
}

export interface CoderThreadUpdateInput extends CoderThreadCreateInput {
  status?: 'active' | 'archived' | 'closed';
}

export interface CoderRuntimeSwitchInput {
  runtime_id: string;
  provider?: string | null;
  model?: string | null;
  reason?: string;
}

export interface CoderReviewPassCreateInput {
  requested_runtime_id?: string | null;
  requested_provider?: string | null;
  requested_model?: string | null;
  title?: string;
  summary_md?: string;
  metadata?: Record<string, unknown>;
}

export interface CoderWorkspacePreferencesUpdateInput {
  advanced_terminal_enabled?: boolean;
  raw_pty_enabled?: boolean;
}

export interface CoderDispatchMessageInput {
  content_md: string;
  runtime_id?: string | null;
  provider?: string | null;
  model?: string | null;
  workspace_context_mode?: string | null;
  metadata?: Record<string, unknown>;
}

export interface CoderLaunchReviewPassInput {
  runtime_id?: string | null;
  provider?: string | null;
  model?: string | null;
  prompt_md?: string | null;
  metadata?: Record<string, unknown>;
}

export interface CoderDispatchResult {
  thread_id: string;
  message: CoderMessage;
  run: CoderRun;
  session: PtySessionSummary;
  detail: CoderThreadDetail;
}

export interface CoderLaunchReviewPassResult {
  thread_id: string;
  review_pass_id: string;
  run: CoderRun;
  session: PtySessionSummary;
  detail: CoderThreadDetail;
}

export async function getCoderWorkspacePreferences(): Promise<CoderWorkspacePreferences> {
  return apiFetch<CoderWorkspacePreferences>('/coder-workspace/preferences', { method: 'GET' });
}

export async function patchCoderWorkspacePreferences(
  input: CoderWorkspacePreferencesUpdateInput
): Promise<CoderWorkspacePreferences> {
  return apiFetch<CoderWorkspacePreferences>('/coder-workspace/preferences', {
    method: 'PATCH',
    body: input,
  });
}

export async function listProjectCoderThreads(projectId: string): Promise<CoderThreadSummary[]> {
  const res = await apiFetch<{ threads: CoderThreadSummary[] }>(
    `/projects/${p(projectId)}/coder-threads`,
    { method: 'GET' }
  );
  return res.threads;
}

export async function createProjectCoderThread(
  projectId: string,
  input: CoderThreadCreateInput
): Promise<CoderThread> {
  return apiFetch<CoderThread>(`/projects/${p(projectId)}/coder-threads`, {
    method: 'POST',
    body: input,
  });
}

export async function getCoderThread(threadId: string): Promise<CoderThreadDetail> {
  return apiFetch<CoderThreadDetail>(`/coder-threads/${p(threadId)}`, { method: 'GET' });
}

export async function patchCoderThread(
  threadId: string,
  input: CoderThreadUpdateInput
): Promise<CoderThread> {
  return apiFetch<CoderThread>(`/coder-threads/${p(threadId)}`, {
    method: 'PATCH',
    body: input,
  });
}

export async function deleteCoderThread(threadId: string): Promise<void> {
  await apiFetch<void>(`/coder-threads/${p(threadId)}`, { method: 'DELETE' });
}

export async function switchCoderThreadRuntime(
  threadId: string,
  input: CoderRuntimeSwitchInput
): Promise<{ thread: CoderThread }> {
  return apiFetch<{ thread: CoderThread }>(`/coder-threads/${p(threadId)}/runtime`, {
    method: 'POST',
    body: input,
  });
}

export async function createCoderReviewPass(
  threadId: string,
  input: CoderReviewPassCreateInput
): Promise<CoderReviewPass> {
  return apiFetch<CoderReviewPass>(`/coder-threads/${p(threadId)}/review-passes`, {
    method: 'POST',
    body: input,
  });
}

export async function launchCoderReviewPass(
  threadId: string,
  reviewPassId: string,
  input: CoderLaunchReviewPassInput = {}
): Promise<CoderLaunchReviewPassResult> {
  return apiFetch<CoderLaunchReviewPassResult>(
    `/coder-threads/${p(threadId)}/review-passes/${p(reviewPassId)}/launch`,
    {
      method: 'POST',
      body: input,
    }
  );
}

export async function getCoderWorkspaceContext(threadId: string): Promise<CoderWorkspaceContext> {
  return apiFetch<CoderWorkspaceContext>(`/coder-threads/${p(threadId)}/context`, {
    method: 'GET',
  });
}

export async function dispatchCoderThreadMessage(
  threadId: string,
  input: CoderDispatchMessageInput
): Promise<CoderDispatchResult> {
  return apiFetch<CoderDispatchResult>(`/coder-threads/${p(threadId)}/dispatch`, {
    method: 'POST',
    body: input,
  });
}
