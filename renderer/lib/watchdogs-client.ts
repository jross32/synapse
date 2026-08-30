import { apiFetch } from './api-client';

export type WatchdogHealth = 'healthy' | 'armed' | 'warning' | 'stopped';

export interface WatchdogProcess {
  pid: number;
  name: string;
  command_line: string;
  status: string;
  uptime_seconds: number;
}

export interface WatchdogTask {
  task_name: string;
  state: string | null;
  hidden: boolean;
  last_run_time: string | null;
  next_run_time: string | null;
  last_task_result: number | null;
}

export interface WatchdogItem {
  id: string;
  name: string;
  kind: string;
  group: string;
  description: string;
  health: WatchdogHealth;
  processes: WatchdogProcess[];
  task: WatchdogTask | null;
  protects: string[];
  protected_by: string[];
  log_available: boolean;
  log_path: string | null;
  latest_log_line: string | null;
  tags: string[];
  console_risk: boolean;
}

export interface WatchdogSnapshot {
  generated_at_epoch: number;
  counts: {
    total: number;
    healthy: number;
    armed: number;
    warning: number;
    stopped: number;
    console_risk: number;
  };
  items: WatchdogItem[];
}

export interface WatchdogLog {
  id: string;
  name: string;
  path: string | null;
  lines: string[];
}

export async function fetchWatchdogs(force = false): Promise<WatchdogSnapshot> {
  return apiFetch<WatchdogSnapshot>(`/system/watchdogs${force ? '?force=true' : ''}`, {
    method: 'GET',
    timeoutMs: 10_000,
  });
}

export async function fetchWatchdogLog(
  id: string,
  lines = 120
): Promise<WatchdogLog> {
  return apiFetch<WatchdogLog>(
    `/system/watchdogs/${encodeURIComponent(id)}/log?lines=${Math.max(
      1,
      Math.min(500, lines)
    )}`,
    { method: 'GET', timeoutMs: 10_000 }
  );
}
