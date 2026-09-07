import { apiFetch } from './api-client';

export type ActiveTaskScheduleKind = 'interval' | 'once';
export type ActiveTaskRunStatus =
  | 'queued'
  | 'running'
  | 'dispatched'
  | 'skipped_overlap'
  | 'failed'
  | 'interrupted';

export interface ActiveTask {
  id: string;
  project_id: string;
  name: string;
  prompt: string;
  dispatch_kind: 'foreman_iteration';
  preferred_runtime: string;
  schedule_kind: ActiveTaskScheduleKind;
  interval_seconds: number | null;
  next_run_at: string | null;
  end_at: string | null;
  max_runs: number | null;
  run_count: number;
  enabled: boolean;
  no_overlap: boolean;
  max_runtime_seconds: number;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_status: string | null;
  last_error: string;
  last_dispatch_ref: string | null;
  created_at: string;
  updated_at: string;
  source: string;
}

export interface ActiveTaskRun {
  id: string;
  task_id: string;
  scheduled_for: string;
  started_at: string | null;
  finished_at: string | null;
  status: ActiveTaskRunStatus;
  manual: boolean;
  dispatch_ref: string | null;
  error: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface ActiveTaskList {
  tasks: ActiveTask[];
  count: number;
}

export interface ActiveTaskSummary {
  count: number;
  enabled: number;
  disabled: number;
  due: number;
  running_or_dispatched: number;
  note: string;
}

export interface ActiveTaskCreateInput {
  project_id: string;
  name: string;
  prompt?: string;
  preferred_runtime?: string;
  schedule_kind?: ActiveTaskScheduleKind;
  interval_seconds?: number | null;
  next_run_at?: string | null;
  end_at?: string | null;
  max_runs?: number | null;
  enabled?: boolean;
  no_overlap?: boolean;
  max_runtime_seconds?: number;
}

export interface ActiveTaskUpdateInput {
  name?: string;
  prompt?: string;
  preferred_runtime?: string;
  schedule_kind?: ActiveTaskScheduleKind;
  interval_seconds?: number | null;
  next_run_at?: string | null;
  end_at?: string | null;
  max_runs?: number | null;
  enabled?: boolean;
  no_overlap?: boolean;
  max_runtime_seconds?: number;
}

const p = encodeURIComponent;

export function listActiveTasks(projectId?: string): Promise<ActiveTaskList> {
  const suffix = projectId ? `?project_id=${p(projectId)}` : '';
  return apiFetch<ActiveTaskList>(`/active-tasks${suffix}`, { method: 'GET' });
}

export function getActiveTaskSummary(): Promise<ActiveTaskSummary> {
  return apiFetch<ActiveTaskSummary>('/active-tasks/summary', { method: 'GET' });
}

export function createActiveTask(input: ActiveTaskCreateInput): Promise<ActiveTask> {
  return apiFetch<ActiveTask>('/active-tasks', { method: 'POST', body: input });
}

export function updateActiveTask(id: string, input: ActiveTaskUpdateInput): Promise<ActiveTask> {
  return apiFetch<ActiveTask>(`/active-tasks/${p(id)}`, { method: 'PATCH', body: input });
}

export function deleteActiveTask(id: string): Promise<void> {
  return apiFetch<void>(`/active-tasks/${p(id)}`, { method: 'DELETE' });
}

export function runActiveTaskNow(id: string): Promise<ActiveTaskRun> {
  return apiFetch<ActiveTaskRun>(`/active-tasks/${p(id)}/run-now`, { method: 'POST' });
}

export function listActiveTaskRuns(id: string, limit = 20): Promise<{ runs: ActiveTaskRun[]; count: number }> {
  return apiFetch(`/active-tasks/${p(id)}/runs?limit=${limit}`, { method: 'GET' });
}
