import { apiFetch } from './api-client';

export type ThreadDisplayStatus = 'active' | 'idle' | 'error' | 'stale' | 'gone' | 'archived';

export interface ThreadPresenceThread {
  id: string;
  work_group_id: string;
  project_id: string;
  session_id: string | null;
  runtime_id: string;
  source: string;
  external_thread_key: string;
  conversation_url: string;
  title: string;
  description: string;
  status: string;
  display_status: ThreadDisplayStatus;
  stale: boolean;
  current_task: string;
  total_work_seconds: number;
  turn_count: number;
  current_turn_started_at: string | null;
  last_activity_at: string;
  last_seen_at: string;
  last_error: string;
  created_at: string;
  updated_at: string;
}

export interface ThreadPresenceGroup {
  id: string;
  project_id: string;
  name: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
  thread_count: number;
  active_count: number;
  idle_count: number;
  error_count: number;
  stale_count: number;
  gone_count: number;
  total_work_seconds: number;
  threads: ThreadPresenceThread[];
}

export interface BrowserThreadObservation {
  external_thread_key: string;
  runtime_id: string;
  browser_tab_id: string;
  conversation_url: string;
  title: string;
  status: ThreadDisplayStatus;
  current_task: string;
  generation_started_at: string | null;
  last_duration_seconds: number | null;
  last_error: string;
  last_seen_at: string;
  tracked_thread_id: string | null;
}

export interface ThreadPresenceOverview {
  generated_at: string;
  stale_after_seconds: number;
  counts: {
    groups: number;
    threads: number;
    tracked_in_progress: number;
    browser_unassigned: number;
    browser_unassigned_active: number;
    in_progress: number;
    active: number;
    idle: number;
    error: number;
    stale: number;
    gone: number;
    archived: number;
  };
  total_work_seconds: number;
  unassigned_browser_threads: BrowserThreadObservation[];
  groups: ThreadPresenceGroup[];
}

export function getThreadPresenceOverview(): Promise<ThreadPresenceOverview> {
  return apiFetch<ThreadPresenceOverview>('/thread-presence/overview', {method: 'GET'});
}
