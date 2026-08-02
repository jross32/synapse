// Client for the AI-activity feed (ADR-0028). Types mirror
// daemon/synapse_daemon/activity.py + routes_activity.py.

import { apiFetch } from './api-client';

/** A renderer NavigationIntent, passed straight to the app's navigate() flow. */
export type NotificationIntent = Record<string, unknown>;

export interface NotificationLink {
  label: string;
  intent: NotificationIntent;
}

/** green | yellow | red | info — drives the status dot colour. */
export type ActivityLevel = 'green' | 'yellow' | 'red' | 'info';

export interface ActivityNotification {
  id: string;
  session_id: string | null;
  seq: number | null;
  kind: string;
  level: ActivityLevel;
  title: string;
  body_md: string;
  links: NotificationLink[];
  token_usage: Record<string, unknown> | null;
  created_at: string;
  read_at: string | null;
}

export interface ActivityFeed {
  notifications: ActivityNotification[];
  unread_count: number;
}

export interface ActivitySession {
  id: string;
  /** Operator-facing number. `null` for a worker nested under a main AI --
   *  those are shown inside their parent, so they take no top-level number. */
  seq: number | null;
  /** The main AI this session runs under; `null` for a root session. */
  parent_session_id?: string | null;
  /** Workers nested under this session (only present on root rows). */
  children?: ActivitySession[];
  child_count?: number;
  project_id: string | null;
  runtime_id: string;
  agent_label: string;
  coder_thread_id: string | null;
  task: string;
  status: string;
  last_intent: string;
  connection_level: ActivityLevel;
  connection_code: string;
  connection_help?: {
    title: string;
    explanation: string;
    remedy: string;
  };
  registered_at: string;
  last_heartbeat_at: string;
  ended_at: string | null;
  stale: boolean;
}

export type ActivityJournalCategory =
  | 'status'
  | 'plan'
  | 'reasoning'
  | 'idea'
  | 'decision'
  | 'action'
  | 'evidence'
  | 'search'
  | 'blocker'
  | 'squad'
  | 'mcp'
  | 'tool'
  | 'result';

export type ActivityJournalStatus =
  | 'planned'
  | 'active'
  | 'success'
  | 'blocked'
  | 'failed'
  | 'info';

export type ActivityAuthority = 'none' | 'observe' | 'control' | 'execute';

export interface ActivityJournalEvent {
  id: string;
  session_id: string | null;
  category: ActivityJournalCategory;
  status: ActivityJournalStatus;
  title: string;
  summary_md: string;
  squad_id: string | null;
  work_item_id: string | null;
  mcp_server_id: string | null;
  tool_name: string | null;
  authority: ActivityAuthority;
  source: string;
  created_at: string;
}

export interface ActivitySquadView {
  squad: Record<string, unknown>;
  work_items: Array<Record<string, unknown>>;
  worker_profiles: Array<{
    work_item_id: string;
    role: Record<string, unknown> | null;
    personality: Record<string, unknown> | null;
    runtime: string | null;
    pty_session_id: string | null;
    coordination_session: ActivitySession | null;
    token_usage: {
      entries: number;
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
    };
    status_changed_at: string;
  }>;
  token_usage: Record<string, unknown>;
}

export type ActivityGoalStatus = 'pending' | 'active' | 'completed' | 'blocked';

export interface ActivityGoal {
  id: string;
  session_id: string;
  title: string;
  detail_md: string;
  status: ActivityGoalStatus;
  position: number;
  created_at: string;
  updated_at: string;
}

export interface ActivitySessionDetail {
  session: ActivitySession;
  squads: ActivitySquadView[];
  notifications: ActivityNotification[];
  journal: ActivityJournalEvent[];
  goals: ActivityGoal[];
}

export function getActivityNotifications(unread = false, limit = 50): Promise<ActivityFeed> {
  return apiFetch<ActivityFeed>(
    `/activity/notifications?unread=${unread ? 'true' : 'false'}&limit=${limit}`,
    { method: 'GET' }
  );
}

export function markNotificationRead(id: string): Promise<ActivityNotification> {
  return apiFetch<ActivityNotification>(`/activity/notifications/${encodeURIComponent(id)}/read`, {
    method: 'POST',
  });
}

export function markAllNotificationsRead(): Promise<{ marked_read: number }> {
  return apiFetch<{ marked_read: number }>('/activity/notifications/read-all', { method: 'POST' });
}

export function getActivitySessions(): Promise<{ sessions: ActivitySession[] }> {
  return apiFetch<{ sessions: ActivitySession[] }>('/activity/sessions', { method: 'GET' });
}

export function getActivitySessionDetail(id: string): Promise<ActivitySessionDetail> {
  return apiFetch<ActivitySessionDetail>(`/activity/sessions/${encodeURIComponent(id)}`, {
    method: 'GET',
  });
}

export function createActivityGoal(
  sessionId: string,
  payload: { title: string; detail_md?: string; status?: ActivityGoalStatus }
): Promise<ActivityGoal> {
  return apiFetch<ActivityGoal>(`/activity/sessions/${encodeURIComponent(sessionId)}/goals`, {
    method: 'POST',
    body: payload,
  });
}

export function updateActivityGoal(
  sessionId: string,
  goalId: string,
  payload: { title?: string; detail_md?: string; status?: ActivityGoalStatus; position?: number }
): Promise<ActivityGoal> {
  return apiFetch<ActivityGoal>(
    `/activity/sessions/${encodeURIComponent(sessionId)}/goals/${encodeURIComponent(goalId)}`,
    { method: 'PATCH', body: payload }
  );
}

export function deleteActivityGoal(sessionId: string, goalId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(
    `/activity/sessions/${encodeURIComponent(sessionId)}/goals/${encodeURIComponent(goalId)}`,
    { method: 'DELETE' }
  );
}
